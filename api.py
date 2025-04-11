import os
from fastapi import FastAPI, HTTPException, File, UploadFile, Form
from pydantic import BaseModel
from typing import List, Optional, Union, Dict
from fastapi.middleware.cors import CORSMiddleware
import google.generativeai as genai
from google.generativeai import types
import requests
from bs4 import BeautifulSoup
from docx import Document
import json
import random
import time
import logging

# --- Setup Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Generation config (currently not passed to generate_content, but available if needed)
generation_config = types.GenerationConfig(
    temperature=0,
    top_p=0.95,
    top_k=40,
    max_output_tokens=1024
)

# --- FastAPI App ---
app = FastAPI(title="CV-Job Matching Service")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# --- Pydantic Models ---
class JobDescription(BaseModel):
    title: str
    description: str
    job_url: Optional[str] = None

class EvaluationRequest(BaseModel):
    cv: str  # Provide your CV as plain text (or use file upload endpoint)
    job_urls: Optional[List[str]] = None
    job_descriptions: Optional[List[JobDescription]] = None
    api_key: str

class EvaluationResult(BaseModel):
    job_title: str
    job_description: str
    job_url: Optional[str] = None
    score_and_explanation: str

class EvaluationResponse(BaseModel):
    evaluations: List[EvaluationResult]

# --- Utility Functions ---
def read_cv_from_text(cv_text: str) -> str:
    """
    Returns the provided plain text CV.
    """
    return cv_text

def read_cv_from_file(cv_file: UploadFile) -> Optional[str]:
    try:
        doc = Document(cv_file.file)
        cv_text = "\n".join([para.text for para in doc.paragraphs])
        return cv_text
    except Exception as e:
        logger.error(f"Error reading CV file: {e}")
        return None

def scrape_all_text(url: str) -> Optional[str]:
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_2) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:134.0) Gecko/20100101 Firefox/134.0",
        "Mozilla/5.0 (Linux; Android 14; Mobile; rv:134.0) Gecko/134.0 Firefox/134.0",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.4 Mobile/15E148 Safari/605.1"
    ]

    headers = {
        'User-Agent': random.choice(user_agents),
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://www.google.com/', # Add a referer
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }

    try:
        time.sleep(random.uniform(1, 5)) # Add random delay
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        return soup.get_text()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching URL {url}: {e}")
        return None

def extract_job_details(text: str, local_model) -> Union[tuple, str]:
    prompt = f"""
    You are given a text describing a position (job requirements, responsibilities, etc.):

    {text}

    Please find and return:
    1. "Title": The recognized job title (for example, "Software Engineer", "Project Manager", "Officer" etc.).
    - If the text does not clearly state a formal job title, you may infer it if there is a clear context (e.g., "Backend Developer" if it talks about backend services).
    - If it is unclear or no valid title is mentioned, use "Unclear".
    2. "Detail": A concise summary of the job requirements and responsibilities.

    Return your answer in the following format (plain text, not JSON):
    Title: <Extracted Job Title>
    Detail: <Extracted job requirements and responsibilities>

    Make sure to:
    - Provide only one job title.
    - Avoid using words like "responsibility" or "qualification" as the title.
    - If the text references multiple roles, select the primary one.
    - Return both "Title" and "Detail" even if one is "Unclear."

    ---

    How to Pick a Correct Job Title:
    1. Look for keywords or phrases that indicate a role (e.g., “manager,” “engineer,” “developer,” etc.).
    2. Confirm there is a clear role or position in the text.
    3. Ensure there is only one main title; if multiple positions are described, pick the most prominent one or return "Unclear."
    4. If no valid title is found, return "Unclear."
    5. Exclude words like "responsibility," "requirement," or "skill" from the title.
    """

    try:
        response = local_model.generate_content(prompt)
        response_text = response.text
        title_start_index = response_text.find("Title:")
        detail_start_index = response_text.find("Detail:")

        if title_start_index != -1 and detail_start_index != -1:
            title = response_text[title_start_index + len("Title:"):detail_start_index].strip()
            detail = response_text[detail_start_index + len("Detail:"):].strip()
        else:
            return f"Error: Could not extract title and detail from response:\n{response_text}"
        
        if title and detail:
            return (title, detail)
        else:
            return f"Error: Extraction failed. Response:\n{response_text}"
    except Exception as e:
        return f"Error: Failed to call Gemini API: {e}"

def scrape_job_details(url: str, local_model) -> Optional[Dict[str, str]]:
    content = scrape_all_text(url)
    if not content:
        return None
    job_data = extract_job_details(content, local_model)
    if isinstance(job_data, tuple) and len(job_data) == 2:
        return {"title": job_data[0], "description": job_data[1]}
    else:
        logger.error(f"Job data extraction error: {job_data}")
        return None

def evaluate_cv_against_job(cv_text: str, job_title: str, job_description: str, local_model) -> str:
    prompt = f"""Please evaluate the following CV against the job description using the rubric provided below. Your output must include an overall score out of 100, a breakdown of scores for each category, and a brief explanation for each component. The output must be in JSON format exactly as specified, with no extra commentary.

    Job Details and CV Input:

    Job Title: {job_title}
    Job Description:
    {job_description}

    CV:
    {cv_text}

    Evaluation Rubric:

    Experience (40 points total)
    Relevance (up to 20 points): How well does the candidate's previous job experience match the responsibilities and requirements stated in the job description?
    Duration & Level (up to 10 points): Consider the number of years and level of seniority in relevant roles.
    Achievements & Progression (up to 10 points): Evaluate the candidate's career progression, accomplishments, and consistency in their career path.

    Skills (40 points total)
    Core Skills Alignment (up to 25 points): Assess whether the key technical and professional skills required for the job are present in the CV.
    Additional Skills (up to 10 points): Consider extra relevant skills that add value to the candidate's profile.
    Certifications/Qualifications (up to 5 points): Evaluate any certifications or formal qualifications that support the candidate's skill set.

    Personality Fit (20 points total)
    Cultural & Team Fit (up to 10 points): Assess indications of a good cultural fit and potential compatibility with team dynamics.
    Communication & Presentation (up to 10 points): Consider the clarity, tone, and overall presentation of the CV as reflective of the candidate's soft skills.

    Instructions:
    Step 1: Evaluate each category (Experience, Skills, Personality) according to the rubric above.
    Step 2: For each category, assign a score and provide a brief explanation summarizing the key factors that influenced the score.
    Step 3: Sum the scores from all categories to generate the overall score (which must be out of 100 and rounded to a multiple of 5).
    Step 4: Provide an overall explanation summarizing the candidate's fit for the job based on your evaluation.

    Output Format (JSON):
    {{
    "overall_score": <score out of 100>,
    "experience": {{
        "score": <score out of 40>,
        "explanation": "<brief explanation>"
    }},
    "skills": {{
        "score": <score out of 40>,
        "explanation": "<brief explanation>"
    }},
    "personality": {{
        "score": <score out of 20>,
        "explanation": "<brief explanation>"
    }},
    "overall_explanation": "<overall summary explanation>"
    }}
    """
    try:
        response = local_model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Error calling Gemini API: {e}"

# --- FastAPI Endpoint ---
@app.post("/evaluate", response_model=EvaluationResponse)
async def evaluate(
    cv: UploadFile = File(...),
    job_urls: Optional[str] = Form(None),
    job_descriptions: Optional[str] = Form(None),
    api_key: str = Form(...)
):
    # Log incoming request details
    logger.info("Received evaluation request")
    logger.info(f"CV filename: {cv.filename}")
    logger.info(f"Job URLs provided: {job_urls is not None}")
    logger.info(f"Job descriptions provided: {job_descriptions is not None}")
    logger.info(f"API key length: {len(api_key) if api_key else 0}")

    # Validate the provided API key
    if not api_key or len(api_key) == 0:
        logger.error("Invalid API key provided")
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    # Configure the local Gemini model
    try:
        genai.configure(api_key=api_key)
        local_model = genai.GenerativeModel("gemini-2.0-flash")
        logger.info("Gemini model configured successfully")
    except Exception as e:
        logger.error(f"Error configuring Gemini model: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error configuring Gemini model: {str(e)}")

    # Read CV file
    try:
        cv_text = read_cv_from_file(cv)
        if not cv_text:
            logger.error(f"Failed to read CV file: {cv.filename}")
            raise HTTPException(status_code=400, detail=f"Unable to read CV file: {cv.filename}. Make sure it's a valid .docx file.")
        logger.info("CV file read successfully")
    except Exception as e:
        logger.error(f"Error reading CV file: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error reading CV file: {str(e)}")

    evaluations = []

    # Process job descriptions
    if job_descriptions:
        try:
            job_descriptions_list = json.loads(job_descriptions)
            logger.info(f"Processing {len(job_descriptions_list)} job descriptions")
            for idx, job in enumerate(job_descriptions_list):
                logger.info(f"Processing job description {idx + 1}")
                job_detail = extract_job_details(job, local_model)
                job_title = job_detail[0]
                job_description = job_detail[1]
                job_url = ""
                
                if not job_title or not job_description:
                    logger.error(f"Missing title or description in job description {idx + 1}")
                    raise HTTPException(status_code=400, detail=f"Job description {idx + 1} is missing title or description")
                
                score_and_explanation = evaluate_cv_against_job(cv_text, job_title, job_description, local_model)
                evaluations.append(EvaluationResult(
                    job_title=job_title,
                    job_description=job_description,
                    job_url=job_url,
                    score_and_explanation=score_and_explanation
                ))
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON format for job_descriptions: {str(e)}")
            raise HTTPException(status_code=400, detail=f"Invalid JSON format for job_descriptions: {str(e)}")
        except Exception as e:
            logger.error(f"Error processing job descriptions: {str(e)}")
            raise HTTPException(status_code=400, detail=f"Error processing job descriptions: {str(e)}")

    # Process job URLs
    if job_urls:
        try:
            job_urls_list = json.loads(job_urls)
            logger.info(f"Processing {len(job_urls_list)} job URLs")
            for idx, url in enumerate(job_urls_list):
                logger.info(f"Processing job URL {idx + 1}: {url}")
                job_detail = scrape_job_details(url, local_model)
                if job_detail:
                    score_and_explanation = evaluate_cv_against_job(cv_text, job_detail["title"], job_detail["description"], local_model)
                    evaluations.append(EvaluationResult(
                        job_title=job_detail["title"],
                        job_description=job_detail["description"],
                        job_url=url,
                        score_and_explanation=score_and_explanation
                    ))
                else:
                    logger.error(f"Failed to scrape job details from URL: {url}")
                    evaluations.append(EvaluationResult(
                        job_title="N/A",
                        job_description="N/A",
                        job_url=url,
                        score_and_explanation=f"Error: Unable to scrape job details from {url}"
                    ))
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON format for job_urls: {str(e)}")
            raise HTTPException(status_code=400, detail=f"Invalid JSON format for job_urls: {str(e)}")
        except Exception as e:
            logger.error(f"Error processing job URLs: {str(e)}")
            raise HTTPException(status_code=400, detail=f"Error processing job URLs: {str(e)}")

    if not evaluations:
        logger.error("No job descriptions or URLs provided for evaluation")
        raise HTTPException(status_code=400, detail="No job descriptions or URLs provided for evaluation")

    logger.info(f"Successfully completed evaluation with {len(evaluations)} results")
    return EvaluationResponse(evaluations=evaluations)

@app.get("/")
async def root():
    return {"message": "Hello World"}

# --- Run the Application ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8081, reload=True)
