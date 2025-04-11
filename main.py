import os
from dotenv import load_dotenv
import google.generativeai as genai
from google.generativeai import types
import requests
from bs4 import BeautifulSoup
from docx import Document
import json

# 1. Read .env file and get the Gemini API key
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    print("Error: GEMINI_API_KEY not found in .env file. Please create a .env file with GEMINI_API_KEY=<your_api_key>")
    exit()

# 2. Initialize Gemini 2.0 API client
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.0-flash')
generation_config = types.GenerationConfig(
    temperature=0,
    top_p=0.95,
    top_k=40,
    max_output_tokens=1024
)

# 3. Function to read CV from a .docx file
def read_cv(cv_file_path):
    """Reads the content of a .docx file (CV)."""
    try:
        doc = Document(cv_file_path)
        return '\n'.join([para.text for para in doc.paragraphs])
    except FileNotFoundError:
        print(f"Error: CV file not found at {cv_file_path}")
        return None

def scrape_all_text(url):
    """Scrapes all text from the given URL from specified tags."""
    headers = {
        'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                       'AppleWebKit/537.36 (KHTML, like Gecko) '
                       'Chrome/103.0.0.0 Safari/537.36')
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        all_text = soup.get_text()

        return all_text
    
    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL {url}: {e}")
        return None
    except Exception as e:
        print(f"Error processing URL {url}: {e}")
        return None
    
def extract_job_details(text):
    global model
    prompt = f"""
    Please extract the job requirements and responsibilities from the following text. Return the "title" and "detail" as separate strings, in plain text, not JSON.

    Text:
    {text}

    Output format example:
    Title: Software Engineer
    Detail: Develop and maintain software applications, participate in code reviews, and collaborate with team members.

    Output format:
    Title: Extracted Job Title
    Detail: Extracted job requirements and responsibilities in detail.
    """

    try:
        response = model.generate_content(prompt)
        response_text = response.text
        title_start_index = response_text.find("Title:")
        detail_start_index = response_text.find("Detail:")

        if title_start_index != -1 and detail_start_index != -1:
            # Extract the title content
            title = response_text[title_start_index + len("Title:") : detail_start_index].strip()

            # Extract the detail content
            detail = response_text[(detail_start_index + len("Title:")):].strip()

            # print(f"Title: '{title}'")
            # print(f"Detail: '{detail}'")
        else:
            print("Could not find 'Title:' or 'Detail:' in the response.")

        if title and detail:
            return (title, detail)
        else:
            return f"Error: Failed to extract title and detail. Original response:\n{response_text}"

    except Exception as e:
        return f"Error: Failed to call the Gemini API: {e}"

    except Exception as e:
        return f"Error: Failed to call the Gemini API: {e}"

def scrape_job_details(url):
    """Scrapes job description and title from a given URL."""
    # Set headers to mimic a real browser
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/103.0.0.0 Safari/537.36'
    }
    
    try:
        content = scrape_all_text(url)
        job_data = extract_job_details(content)
        print(job_data)
        return {"title": job_data[0], "description": job_data[1]}
    
    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL {url}: {e}")
        return None
    except Exception as e:
        print(f"Error processing URL {url}: {e}")
        return None

# 5. Array to hold job descriptions and titles
job_details_array = []

# Example list of job URLs
job_urls = [
    # "https://hk.jobsdb.com/job/82860937?cid=company-profile&ref=company-profile",
    # "https://tw.linkedin.com/jobs/view/mechanical-engineer-at-lenovo-4167163972?trk=public_jobs_topcard-title",
    # "https://hk.jobsdb.com/job/82577570?ref=search-standalone&type=standard&origin=showNewTab#sol=ecb978fad41c57573c642012cb3f14b2cea2b3ba",
    "https://hk.bebee.com/job/03fcd5dc910623d76e4eb0b32d7af7ac"
]

# Scrape job details from each URL
for url in job_urls:
    details = scrape_job_details(url)
    if details:
        job_details_array.append(details)

print("Extracted Job Details:")
for job in job_details_array:
    print(f"- Title: {job['title']}")
    print(f"  Description: {job['description'][:100]}...")

# 6. Read the CV file
cv_file = "TestCV.docx"  # Replace with the actual path to your CV file
cv_text = read_cv(cv_file)

if cv_text:
    job_scores = []

    # 7. Feed CV and job details to Gemini for scoring
    for job_detail in job_details_array:
        prompt = f"""Please evaluate the following CV against the job description using the rubric provided below. Your output must include an overall score out of 100, a breakdown of scores for each category, and a brief explanation for each component. The output must be in JSON format exactly as specified, with no extra commentary.

                Job Details and CV Input:

                Job Title: {job_detail['title']}
                Job Description:
                {job_detail['description']}

                CV:
                {cv_text}

                Evaluation Rubric:

                Experience (40 points total)

                Relevance (up to 20 points): How well does the candidate’s previous job experience match the responsibilities and requirements stated in the job description?
                Duration & Level (up to 10 points): Consider the number of years and level of seniority in relevant roles.
                Achievements & Progression (up to 10 points): Evaluate the candidate’s career progression, accomplishments, and consistency in their career path.
                Skills (40 points total)

                Core Skills Alignment (up to 25 points): Assess whether the key technical and professional skills required for the job are present in the CV.
                Additional Skills (up to 10 points): Consider extra relevant skills that add value to the candidate’s profile.
                Certifications/Qualifications (up to 5 points): Evaluate any certifications or formal qualifications that support the candidate’s skill set.
                Personality Fit (20 points total)

                Cultural & Team Fit (up to 10 points): Assess indications of a good cultural fit and potential compatibility with team dynamics.
                Communication & Presentation (up to 10 points): Consider the clarity, tone, and overall presentation of the CV as reflective of the candidate’s soft skills.
                Instructions:

                Step 1: Evaluate each category (Experience, Skills, Personality) according to the rubric above.
                Step 2: For each category, assign a score and provide a brief explanation summarizing the key factors that influenced the score.
                Step 3: Sum the scores from all categories to generate the overall score (which must be out of 100 and rounded to a multiple of 5).
                Step 4: Provide an overall explanation summarizing the candidate’s fit for the job based on your evaluation.
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

                Important:

                Use deterministic settings (e.g., a low temperature value) to ensure consistent results for identical inputs.
                Adhere strictly to the JSON format without any additional text outside of it.
        """

        try:
            response = model.generate_content(prompt)
            score_and_explanation = response.text
            job_scores.append({"job_title": job_detail['title'], "score_and_explanation": score_and_explanation})
            print(f"\n--- Matching Score for '{job_detail['title']}' ---")
            print(score_and_explanation)

        except Exception as e:
            print(f"Error calling Gemini API for '{job_detail['title']}': {e}")

    print("\n--- Overall Job Matching Scores ---")
    for score_data in job_scores:
        print(f"- Job Title: {score_data['job_title']}")
        print(f"  Score and Explanation: {score_data['score_and_explanation']}")
else:
    print("Could not read the CV file. Skipping job matching.")
