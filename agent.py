import logging
import os
import random
import json
import time
from typing import Union, Tuple, Optional, Dict, Any

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Importing LangChain components
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
# from langchain_google_genai import ChatGoogleGenerativeAI # Keep if needed, but example focuses on OpenAI
from langchain_core.tools import tool
from langchain_community.document_loaders import Docx2txtLoader
from langchain.agents import AgentExecutor, create_openai_tools_agent # Use standard agent creation
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder # For structured prompts

# ---------------- Logging Setup ----------------
logging.basicConfig(
    level=logging.INFO, # Set to INFO for production, DEBUG for detailed tracing
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
# Get logger for specific modules if needed, or use root logger
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING) # Quieten noisy libraries
logging.getLogger("langchain_community").setLevel(logging.WARNING)


# ---------------- Environment Setup ----------------
load_dotenv()

# Validate API keys
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
# GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") # Keep if needed
if not OPENAI_API_KEY:
    logger.critical("OPENAI_API_KEY not found in environment variables.")
    raise EnvironmentError("OPENAI_API_KEY must be set.")
# if not GEMINI_API_KEY:
#     logger.critical("GEMINI_API_KEY not found in environment variables.")
#     raise EnvironmentError("GEMINI_API_KEY must be set.")

# ---------------- LLM Initialization ----------------
# Consider gpt-4o for potentially better reasoning if mini struggles
llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0, # Low temp for consistent reasoning/tool use
    max_tokens=None,
    timeout=None,
    max_retries=2,
)
logger.info(f"Initialized LLM: {llm.model_name}")

# ---------------- Tool Definitions ----------------
# Make docstrings very clear for the agent
@tool
def jobsdb_search(keywords: str, base_keywords: Optional[str] = None, page: int = 1) -> str:
    """
    Searches for job listings on JobsDB Hong Kong based on primary keywords.
    Optionally use 'base_keywords' for broader context if primary keywords are too narrow.
    Specify the 'page' number for pagination (default is 1). Returns a list of job summaries.
    Use this first to find potentially relevant job IDs.
    Args:
        keywords (str): Specific keywords for the job search (e.g., "software engineer python").
        base_keywords (Optional[str]): Broader keywords if needed (e.g., "software development"). Defaults to None.
        page (int): The page number of results to fetch (default is 1).
    """
    try:
        logger.info(f"Initiating JobsDB search. Keywords: '{keywords}', Base Keywords: '{base_keywords}', Page: {page}")
        # Use base_keywords if provided, otherwise fallback to keywords or leave empty if None
        base_kw_param = base_keywords if base_keywords else keywords if keywords else ""
        kw_param = keywords if keywords else ""

        jobsdb_url = (
            f"https://hk.jobsdb.com/api/jobsearch/v5/search?siteKey=HK-Main&sourcesystem=houston"
            f"&page={page}&keywords={kw_param.replace(' ', '+')}&pageSize=30&include=seodata,relatedsearches,joracrosslink,gptTargeting,pills"
            f"&baseKeywords={base_kw_param.replace(' ', '+')}&locale=en-HK"
        )
        logger.debug(f"Requesting URL: {jobsdb_url}")
        response = requests.get(jobsdb_url, timeout=20) # Increased timeout
        response.raise_for_status()

        data = response.json()
        jobs_data = data.get("data", [])
        if not jobs_data:
            logger.warning(f"No job data found for keywords: '{keywords}' on page {page}.")
            return "No jobs found for these criteria on this page."

        formatted_jobs = f"Found {len(jobs_data)} jobs (Page {page}):\n"
        for job in jobs_data:
            formatted_jobs += "=" * 50 + "\n"
            formatted_jobs += format_job(job) + "\n"

        logger.info(f"Successfully retrieved {len(jobs_data)} job summaries.")
        # Limit output length if necessary, but provide enough info
        # return formatted_jobs[:3000] + "... (truncated)" if len(formatted_jobs) > 3000 else formatted_jobs
        return formatted_jobs # Return full results for now

    except requests.exceptions.RequestException as e:
        logger.error(f"HTTP Error searching JobsDB: {e}")
        return f"Error: Could not connect to JobsDB or received an error: {e}"
    except json.JSONDecodeError as e:
        logger.error(f"JSON Parsing Error for JobsDB response: {e}")
        return f"Error: Could not parse the response from JobsDB."
    except Exception as e:
        logger.error(f"Unexpected error searching JobsDB: {e}", exc_info=True)
        return f"Error: An unexpected error occurred during JobsDB search: {e}"

@tool
def linkedin_search(keywords: str, location: str, page: int = 1) -> str:
    """
    Searches for job listings on LinkedIn based on the provided keywords.
    This is a placeholder function and does not perform actual LinkedIn searches.
    Args:
        keywords (str): Specific keywords for the job search (e.g., "software engineer python").
        location (str): Location for the job search (e.g., "Hong Kong").
    """
    logger.info(f"LinkedIn search initiated with keywords: {keywords}, location: {location}")
    list_url = (
        f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
        f"?keywords={keywords.replace(' ', '%20')}&location={location.replace(' ', '%20')}"
        f"&rk=homepage-jobseeker_brand-discovery_intent-module-secondBtn&start={(page - 1) * 25}"
    )
    logger.info(f"LinkedIn URL: {list_url}")

    response_text = scrape_full_html(list_url)
    try:
        soup = BeautifulSoup(response_text, 'html.parser')
    except Exception as e:
        logger.error(f"Error parsing HTML: {e}")
        return [], "Error parsing LinkedIn response."

    # Extract information
    job_cards = soup.find_all('div', class_='base-card')

    jobs = []
    for card in job_cards:
        # Extract job ID from job link or attribute
        job_id = card.get('data-entity-urn').split(":")[3]
        job_url = f"https://hk.linkedin.com/jobs/view/{job_id}" # Construct URL from ID
        title_tag = card.find('span', class_='sr-only')
        company_tag = card.find('a', class_='hidden-nested-link')
        location_tag = card.find('span', class_='job-search-card__location')
        date_tag = card.find('time', class_='job-search-card__listdate')

        job = {
            "job_id": job_id or "N/A",
            "title": title_tag.text.strip() if title_tag else "N/A",
            "company": company_tag.text.strip() if company_tag else "N/A",
            "location": location_tag.text.strip() if location_tag else "N/A",
            "posted": date_tag.text.strip() if date_tag else "N/A",
            "url": job_url or "N/A"
        }

        jobs.append(job)

    # Return friendly format
    if not jobs:
        return jobs, "No job postings found."

    job_strs = []
    for idx, job in enumerate(jobs, 1):
        job_str = (
            f"Job #{idx} — ID: {job['job_id']}\n"
            f"Title    : {job['title']}\n"
            f"Company  : {job['company']}\n"
            f"Location : {job['location']}\n"
            f"Posted   : {job['posted']}\n"
            # f"Link     : {job['url']}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        job_strs.append(job_str)

    formatted_jobs = "\n".join(job_strs)
    return formatted_jobs

@tool
def extract_job_details(job_id: str, platform: str) -> str:
    """
    Extracts the full job title and a concise summary of requirements and responsibilities
    for a specific job ID obtained from either 'jobsdb_search' or 'linkedin_search'.
    It scrapes the job page and uses an LLM to extract the details.
    Use this *after* identifying a promising job ID from search results.

    Args:
        job_id (str): The specific ID of the job (e.g., "JHK100003009123456" for JobsDB, or a numerical ID like "3881234567" for LinkedIn).
        platform (str): The platform the job ID belongs to. Must be 'jobsdb' or 'linkedin'.
    """
    platform = platform.lower()
    logger.info(f"Extracting details for {platform.upper()} job ID: {job_id}")

    if platform == 'jobsdb':
        url = f"https://hk.jobsdb.com/job/{job_id}"
    elif platform == 'linkedin':
        # Assumes job_id is the numerical ID. Construct the standard view URL.
        # Using hk.linkedin as per linkedin_search, adjust domain if needed based on location context.
        url = f"https://hk.linkedin.com/jobs/view/{job_id}"
    else:
        logger.error(f"Invalid platform '{platform}' specified for job ID {job_id}.")
        return "Error: Invalid platform specified. Must be 'jobsdb' or 'linkedin'."

    text = scrape_all_text(url)
    if not text or text.startswith("Error:"): # Check if scraping failed or returned an error string
        error_message = f"Error: Unable to scrape text from {url} for {platform.upper()} job ID {job_id}. Cannot extract details. Reason: {text}"
        logger.error(error_message)
        # Return the scraping error directly
        return error_message if text.startswith("Error:") else f"Error: Unable to scrape text from {url} for {platform.upper()} job ID {job_id}. Empty content received."


    # Limit text size sent to LLM if needed (e.g., first 15000 chars)
    max_chars = 15000
    if len(text) > max_chars:
        logger.warning(f"{platform.upper()} job description text long ({len(text)} chars), truncating to {max_chars} for LLM analysis.")
        text = text[:max_chars]

    # Consistent prompt for extraction
    prompt = f"""
    Given the following text scraped from a job posting page ({platform.upper()}):
    --- START TEXT ---
    {text}
    --- END TEXT ---

    Analyze the text and extract the following information:
    1.  "Title": The full, specific job title mentioned in the posting (e.g., "Senior Software Engineer (Backend, Java)").
    2.  "Summary": A concise summary (2-4 sentences) covering the core responsibilities and key requirements (skills, experience level, qualifications) mentioned. Focus on actionable details relevant for matching with a CV.

    Return the result ONLY in the following JSON format:
    ```json
    {{
    "title": "...",
    "summary": "..."
    }}
    ```
    If the title or summary cannot be reliably extracted from the provided text, use the string "Not Found" as the value. Do not add any explanations outside the JSON structure.
    """
    try:
        logger.debug(f"Invoking LLM for {platform.upper()} job detail extraction (ID: {job_id}).")
        # Assuming 'llm' is your Langchain LLM client and HumanMessage is imported
        messages = [HumanMessage(content=prompt)]
        response = llm.invoke(messages)
        response_content = response.content.strip()

        logger.debug(f"Raw LLM response for extraction (Job ID: {job_id}):\n{response_content}")

        # Attempt to parse the JSON response
        try:
            # Clean potential markdown code fences
            if response_content.startswith("```json"):
                response_content = response_content[7:]
            if response_content.endswith("```"):
                response_content = response_content[:-3]
            response_content = response_content.strip()

            # Handle potential escape sequences if LLM adds them
            response_content = response_content.replace('\\n', '\n').replace('\\"', '"')

            details_json = json.loads(response_content)
            title = details_json.get("title", "Extraction Error: Title Missing")
            summary = details_json.get("summary", "Extraction Error: Summary Missing")

            if title == "Not Found" and summary == "Not Found":
                logger.warning(f"LLM indicated title and summary not found for {platform.upper()} job {job_id}.")
                return f"Platform: {platform.upper()}\nJob ID: {job_id}\nStatus: Could not extract title or summary from the job page content."
            elif title == "Not Found":
                 logger.warning(f"LLM indicated title not found for {platform.upper()} job {job_id}.")
                 title = "Title Not Found" # Use clearer status
            elif summary == "Not Found":
                 logger.warning(f"LLM indicated summary not found for {platform.upper()} job {job_id}.")
                 summary = "Summary Not Found" # Use clearer status


            result_str = f"Platform: {platform.upper()}\nJob ID: {job_id}\nTitle: {title}\nSummary: {summary}"
            logger.info(f"Successfully extracted details for {platform.upper()} job ID {job_id}.")
            return result_str

        except json.JSONDecodeError as json_e:
            error_message = f"Error: Failed to parse JSON response from LLM for {platform.upper()} job {job_id}. Raw response: '{response_content}'. Error: {json_e}"
            logger.error(error_message)
            # Fallback: Return raw response if parsing fails, indicating an issue
            return f"Platform: {platform.upper()}\nJob ID: {job_id}\nStatus: Error processing LLM response. Raw output: {response_content}"
        except Exception as parse_e:
             error_message = f"Error: Unexpected error parsing LLM response for {platform.upper()} job {job_id}. Error: {parse_e}"
             logger.error(error_message)
             return f"Platform: {platform.upper()}\nJob ID: {job_id}\nStatus: Error processing LLM response. Details: {parse_e}"


    except Exception as e:
        # Catch errors during the LLM call itself
        error_message = f"Error: LLM invocation failed during job detail extraction for {platform.upper()} job {job_id}: {e}"
        logger.error(error_message, exc_info=True)
        return error_message

# ---------------- Helper Functions ----------------
# (format_job, scrape_all_text, read_cv remain largely the same, added logging)
def format_job(job: dict) -> str:
    """Format and return job details from a job dictionary (search result)."""
    title = job.get("title", "N/A")
    company = job.get("companyName", "N/A")
    advertiser = job.get("advertiser", {}).get("description", "N/A")
    jobsdb_id = job.get("id", "N/A")
    locations = ", ".join(loc.get("label", "N/A") for loc in job.get("locations", []))
    bullet_points = job.get("bulletPoints", [])
    teaser = job.get("teaser", "")
    work_types = ", ".join(job.get("workTypes", []))
    work_arrangements_data = job.get("workArrangements", {}).get("data", [])
    work_arrangements = ", ".join(
        arr.get("label", {}).get("text", "N/A") for arr in work_arrangements_data
    ) if work_arrangements_data else "N/A" # Handle empty list
    salary = job.get("salary", "N/A") # Often "N/A" or range

    formatted = (
        f"Job ID          : {jobsdb_id}\n" # Consistent spacing
        f"Job Title       : {title}\n"
        f"Company         : {company}\n"
        f"Advertiser      : {advertiser}\n"
        f"Locations       : {locations}\n"
        f"Salary          : {salary}\n"
        f"Teaser          : {teaser}\n"
        f"Bullet Points   :\n"
    )
    if bullet_points:
        for bp in bullet_points:
            formatted += f"  - {bp}\n"
    else:
        formatted += "  N/A\n"
    formatted += (
        f"Work Types      : {work_types or 'N/A'}\n"
        f"Work Arrangements: {work_arrangements}\n"
    )
    # logger.debug(f"Formatted job summary for ID {jobsdb_id}") # Log less verbosely
    return formatted

def scrape_all_text(url: str) -> Optional[str]:
    """
    Scrape and return all text from the given URL using randomized user-agent and delay.
    Returns error message string on failure.
    """
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3.1 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0"
    ]
    headers = {
        'User-Agent': random.choice(user_agents),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Referer': 'https://hk.jobsdb.com/', # More specific referer
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'DNT': '1', # Do Not Track
        'Sec-GPC': '1', # Global Privacy Control
    }
    try:
        delay = random.uniform(1.5, 4.0) # Slightly longer delay
        logger.debug(f"Scraping URL: {url} (Delay: {delay:.2f}s)")
        time.sleep(delay)
        response = requests.get(url, headers=headers, timeout=20) # Increased timeout
        response.raise_for_status() # Check for HTTP errors

        # Check content type
        content_type = response.headers.get('Content-Type', '').lower()
        if 'html' not in content_type:
            logger.warning(f"Non-HTML content type '{content_type}' received from {url}")
            # Decide how to handle - maybe return empty or specific error
            return f"Error: Received non-HTML content from {url}"

        soup = BeautifulSoup(response.content, 'html.parser')

        # Improve text extraction (remove script/style, better spacing)
        for element in soup(["script", "style", "header", "footer", "nav", "aside"]):
            element.decompose()
        text = soup.get_text(separator='\n', strip=True)

        logger.debug(f"Successfully scraped text from {url} (Length: {len(text)}).")
        return text
    except requests.exceptions.Timeout:
        logger.error(f"Timeout error fetching URL {url}")
        return f"Error: Timeout occurred while trying to fetch {url}"
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error fetching URL {url}: {e}")
        return f"Error: Failed to fetch {url} due to network or HTTP issue: {e}"
    except Exception as e:
        logger.error(f"Unexpected error scraping URL {url}: {e}", exc_info=True)
        return f"Error: An unexpected error occurred during scraping: {e}"

def scrape_full_html(url: str) -> Optional[str]:
    """
    Scrape and return all text from the given URL using randomized user-agent and delay.
    Returns error message string on failure.
    """
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3.1 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0"
    ]
    headers = {
        'User-Agent': random.choice(user_agents),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'DNT': '1', # Do Not Track
        'Sec-GPC': '1', # Global Privacy Control
    }
    try:
        response = requests.get(url, headers=headers) # Increased timeout
        response.raise_for_status() # Check for HTTP errors

        return response.text
    except requests.exceptions.Timeout:
        logger.error(f"Timeout error fetching URL {url}")
        return f"Error: Timeout occurred while trying to fetch {url}"
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error fetching URL {url}: {e}")
        return f"Error: Failed to fetch {url} due to network or HTTP issue: {e}"
    except Exception as e:
        logger.error(f"Unexpected error scraping URL {url}: {e}", exc_info=True)
        return f"Error: An unexpected error occurred during scraping: {e}"

def read_cv(cv_file_path: str) -> Optional[str]:
    """Read and return the content of a .docx file (CV)."""
    if not os.path.exists(cv_file_path):
        logger.error(f"CV file not found at {cv_file_path}")
        return None
    if not cv_file_path.lower().endswith(".docx"):
         logger.error(f"Invalid file type. Only .docx files are supported. Path: {cv_file_path}")
         return None
    try:
        logger.info(f"Reading CV file from {cv_file_path}")
        loader = Docx2txtLoader(cv_file_path)
        docs = loader.load() # Returns a list of Document objects
        if not docs:
             logger.warning(f"No content extracted from CV file: {cv_file_path}")
             return "" # Return empty string if no content

        content = "\n".join(d.page_content for d in docs if hasattr(d, 'page_content'))
        logger.info(f"Successfully read CV file (Length: {len(content)}).")
        return content
    except Exception as e:
        logger.error(f"Error reading CV file {cv_file_path}: {e}", exc_info=True)
        return None

# ---------------- Prompt Template ----------------

# Define the prompt template for the agent
# This guides the agent's reasoning process (Chain of Thought)
prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are an expert Recruitment Assistant specializing in the Hong Kong job market.
Your goal is to find the *single best* job match for the user based on their provided CV.

Follow these steps carefully:

1.  **Analyze CV:** Thoroughly read the user's CV provided in the input. Identify key skills, years of experience, primary job functions, seniority level, industries worked in, and any stated career goals or salary expectations (if mentioned).
2.  **Develop Search Strategy:** Based on the CV analysis, determine the most relevant job titles and skills keywords to search for on JobsDB. Consider variations (e.g., "Software Engineer", "Backend Developer", "Java Developer"). Decide if 'base_keywords' are needed for broader context.
3.  **Initial Search:** Use the `jobsdb_search` tool with the best keywords identified. Start with page 1.
4.  **Evaluate Search Results:** Examine the job summaries returned by the search. Do they seem relevant based on your CV analysis? Are there any promising candidates? Note down the Job IDs of 1-3 *most promising* jobs.
5.  **Refine Search (If Necessary):** If the initial search results are poor (irrelevant, too few, too broad), *think* about why. Adjust the keywords (more specific, broader, different terms?) or try page 2 (`page=2` argument in `jobsdb_search`). Explain your reasoning for refining the search. Perform the search again with the refined criteria. Evaluate the new results. Only proceed if you have promising candidates. If multiple searches fail, inform the user.
6.  **Extract Details:** For the 1-3 most promising Job IDs identified, use the `extract_jobdb_details` tool *one by one* for each ID to get more detailed information (title, summary of responsibilities/requirements).
7.  **Compare and Analyze:** Critically compare the extracted details of the promising jobs against the user's CV (skills, experience, level). Evaluate the degree of match for each. Consider which aspects align well and where there might be gaps.
8.  **Final Recommendation:** Based on your comparison, select the *single best* job match. Explain *why* it's the best match, referencing specific points from both the job details and the user's CV. Provide the Job ID, Title, Company, and a summary of why it fits. If no suitable job is found after diligent searching and analysis, clearly state that and explain why (e.g., "No jobs found matching required seniority in X field").

You have access to the following tools:""",
        ),
        # Tool descriptions are automatically added by create_openai_tools_agent
        MessagesPlaceholder(variable_name="chat_history", optional=True), # If you want conversational ability later
        ("human", "{input}"), # User query + CV goes here
        MessagesPlaceholder(variable_name="agent_scratchpad"), # Agent's internal work (thoughts, tool calls/results)
    ]
)


# ---------------- Agent and Executor Initialization ----------------
# Define the tools the agent can use
tools = [jobsdb_search, extract_job_details, linkedin_search]

# Create the agent using the LLM, tools, and prompt
agent = create_openai_tools_agent(llm, tools, prompt)

# Create the AgentExecutor to run the agent
# verbose=True shows the agent's thought process (Chain of Thought)
agent_executor = AgentExecutor(
    agent=agent,
    tools=tools,
    verbose=True, # Set to True to see the detailed reasoning steps
    handle_parsing_errors=True, # Gracefully handles LLM output errors
    max_iterations=15 # Increase max iterations for potentially complex searches
)
logger.info("Agent and Executor initialized.")

# ---------------- Running the Agent ----------------
# print(linkedin_search("software engineer", "Hong Kong")) # Example call to LinkedIn search
if __name__ == "__main__":
    cv_path = "TestCV.docx"  # <<< IMPORTANT: Update with your actual CV file path
    logger.info(f"Attempting to load CV from: {cv_path}")
    cv_content = read_cv(cv_file_path=cv_path)

    if cv_content is None: # Check for None specifically, as empty string is handled
        logger.critical("Failed to read CV content. Please check the file path and format. Exiting.")
        exit(1)
    elif not cv_content.strip(): # Check if content is just whitespace
         logger.warning(f"CV file '{cv_path}' was read but appears to be empty or contains only whitespace.")
         # Decide if you want to exit or proceed without CV content
         # For this agent, CV is essential, so we exit.
         logger.critical("CV content is empty. Agent requires CV details to function. Exiting.")
         exit(1)


    # Combine the user's request and the CV content into the input
    # This structure makes it clear to the agent what the main task is and what data to use
    initial_query_with_cv = f"""
User Request: Find the single best job match for me in Hong Kong using my CV details below. Analyze my experience and skills to guide your search and recommendation.

My CV Content:
--- START CV ---
{cv_content}
--- END CV ---
"""

    logger.info("Invoking the agent executor...")
    start_time = time.time()
    try:
        # Run the agent executor
        response = agent_executor.invoke({"input": initial_query_with_cv})
        end_time = time.time()
        logger.info(f"Agent execution finished in {end_time - start_time:.2f} seconds.")

        # The final answer is in the 'output' key
        final_answer = response.get("output", "Agent did not produce a final output.")

        print("\n" + "=" * 30 + " Final Recommendation " + "=" * 30)
        print(final_answer)
        print("=" * (60 + len(" Final Recommendation ")))

    except Exception as e:
        end_time = time.time()
        logger.critical(f"An error occurred during agent execution after {end_time - start_time:.2f} seconds: {e}", exc_info=True)
        print(f"\nAn error occurred: {e}")