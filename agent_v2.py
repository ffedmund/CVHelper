import logging
import getpass
import os
import random
import json
import time
from typing import Union, Tuple, Optional, Dict, Any
import re # Import regex

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Importing LangChain components
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI # Keep if needed
from langchain_core.tools import tool
from langchain_community.document_loaders import Docx2txtLoader
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

# ---------------- Logging Setup ----------------
logging.basicConfig(
    level=logging.INFO, # Set to INFO for production, DEBUG for detailed tracing
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING) # Quieten noisy libraries
logging.getLogger("langchain_community").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING) # Quieten requests library


# ---------------- Environment Setup ----------------
# load_dotenv()

# Validate API keys
# OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
# if not OPENAI_API_KEY:
#     logger.critical("OPENAI_API_KEY not found in environment variables.")
#     raise EnvironmentError("OPENAI_API_KEY must be set.")

# GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# if not GEMINI_API_KEY:
#     os.environ["GEMINI_API_KEY"] = getpass.getpass("Enter your Google AI API key: ")
# print(f"Google AI API key set.: {GEMINI_API_KEY}")
# ---------------- LLM Initialization ----------------
# llm = ChatOpenAI(
#     model="gpt-4o-mini", # Use gpt-4o if mini struggles with complex reasoning/scraping instructions
#     temperature=0.1, # Slightly increased temp for potentially broader search ideas
#     max_tokens=None,
#     timeout=None,
#     max_retries=3, # Increase retries slightly
# )
# logger.info(f"Initialized LLM: {llm.model_name}")
# llm = ChatGoogleGenerativeAI(
#     model="gemini-2.0-flash-001",
#     temperature=0,
#     max_tokens=None,
#     timeout=None,
#     max_retries=3,
#     google_api_key=GEMINI_API_KEY,
#     # other params...
# )

# ---------------- Tool Definitions ----------------
@tool
def jobsdb_search(keywords: str, location: str = "Hong Kong", page: int = 1) -> str:
    """
    Searches for job listings on JobsDB Hong Kong based on keywords and location.
    Use this tool to get an initial list of potentially relevant jobs from JobsDB.
    Specify the 'page' number for pagination (default is 1).
    Returns a list of job summaries including Job IDs.

    Args:
        keywords (str): Specific keywords for the job search (e.g., "software engineer python", "project manager fintech startup").
        location (str): The target location (default is "Hong Kong"). Specify if different.
        page (int): The page number of results to fetch (default is 1).
    """
    try:
        logger.info(f"Initiating JobsDB search. Keywords: '{keywords}', Location: '{location}', Page: {page}")

        # Basic keyword cleaning/encoding
        kw_param = requests.utils.quote(keywords)
        loc_param = requests.utils.quote(location)

        # Note: The JobsDB API structure might change. This is based on observed patterns.
        # The 'baseKeywords' seemed less critical than primary keywords in testing, simplifying.
        jobsdb_url = (
            f"https://hk.jobsdb.com/api/jobsearch/v5/search?siteKey=HK-Main&sourcesystem=houston"
            f"&page={page}&keywords={kw_param}&pageSize=25"
            f"&locale=en-HK&location={loc_param}"
            f"&include=seodata,jobDetailScore" # Simplified includes
        )
        logger.debug(f"Requesting JobsDB URL: {jobsdb_url}")

        # Use a session for potential connection reuse
        with requests.Session() as session:
            session.headers.update({ # Add basic headers
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
                'Accept': 'application/json',
            })
            response = session.get(jobsdb_url, timeout=25) # Increased timeout
            response.raise_for_status() # Check for HTTP errors (4xx, 5xx)

        data = response.json()
        jobs_data = data.get("data", [])

        if not jobs_data:
            logger.warning(f"No JobsDB jobs found for keywords: '{keywords}', Location: '{location}', Page: {page}.")
            return f"No JobsDB jobs found for '{keywords}' in {location} on page {page}."

        formatted_jobs = f"Found {len(jobs_data)} JobsDB jobs (Page {page}) for '{keywords}' in {location}:\n"
        for job in jobs_data:
            formatted_jobs += "=" * 50 + "\n"
            formatted_jobs += format_job(job) + "\n" # Use helper function

        logger.info(f"Successfully retrieved {len(jobs_data)} job summaries from JobsDB.")
        # Return full results for the agent to evaluate
        return formatted_jobs

    except requests.exceptions.Timeout:
        logger.error(f"Timeout error searching JobsDB for '{keywords}'. URL: {jobsdb_url}")
        return f"Error: Timeout occurred while searching JobsDB for '{keywords}'."
    except requests.exceptions.RequestException as e:
        logger.error(f"HTTP Error searching JobsDB: {e}. URL: {jobsdb_url}")
        # Include status code if available
        status_code = e.response.status_code if e.response is not None else 'N/A'
        return f"Error: Could not connect to JobsDB or received an error (Status: {status_code}) for '{keywords}': {e}"
    except json.JSONDecodeError as e:
        logger.error(f"JSON Parsing Error for JobsDB response for '{keywords}': {e}. Response text: {response.text[:500]}") # Log start of bad response
        return f"Error: Could not parse the response from JobsDB for '{keywords}'."
    except Exception as e:
        logger.error(f"Unexpected error searching JobsDB for '{keywords}': {e}", exc_info=True)
        return f"Error: An unexpected error occurred during JobsDB search: {e}"


@tool
def linkedin_search(keywords: str, location: str = "Hong Kong", num_results: int = 25) -> str:
    """
    Searches for job listings on LinkedIn using guest access.
    This function scrapes job postings based on the provided keywords and location,
    returning a formatted summary of the results. It iteratively fetches job listings
    until the desired number of results is reached or no more jobs are found.

    Args:
        keywords (str): Specific keywords for the job search (e.g., "software engineer python").
        location (str): Location for the job search (e.g., "Hong Kong"). Default is "Hong Kong".
        num_results (int): The maximum number of job results to retrieve. Default is 25.

    Returns:
        str: A formatted string summarizing the job postings found, including title,
             company, location, posted date, and a direct job URL. Returns an error
             message if scraping fails or no jobs are found.
    """
    
    # Log the start of the search
    logger.info(f"LinkedIn search initiated with keywords: '{keywords}', location: '{location}', number of results: {num_results}")
    try:
        jobs = []
        while len(jobs) < num_results:
            # Construct the LinkedIn Guest API URL with URL-encoded parameters.
            list_url = (
                f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
                f"?keywords={keywords.replace(' ', '%20')}&location={location.replace(' ', '%20')}"
                f"&start={len(jobs)}"
            )
            logger.info(f"Constructed LinkedIn URL: {list_url}")
            # Scrape the raw HTML from the constructed URL
            with requests.Session() as session:
                user_agents = [
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36 Edg/134.0.3124.95",
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
                ]
                session.headers.update({ # Add basic headers
                    'User-Agent': random.choice(user_agents),
                    'Accept': 'application/json',
                })
                response = session.get(list_url, timeout=25) # Increased timeout
                response.raise_for_status() # Check for HTTP errors (4xx, 5xx)
            logger.info(f"Received HTML response from LinkedIn (first 1000 chars): {response.text[:1500] if response.text else 'None'}")
            
            # Parse the HTML using BeautifulSoup
            try:
                soup = BeautifulSoup(response.text, 'html.parser')
            except Exception as e:
                logger.error(f"Error parsing HTML from LinkedIn: {e}")
                return "Error parsing LinkedIn response."
            
            # Extract job listing containers using the original logic (searching for base-card divs)
            job_cards = soup.find_all('li')
            logger.debug(f"Found {len(job_cards)} job card elements.")
            if len(job_cards) == 0:
                logger.warning("No job cards found in LinkedIn response. Ending search.")
                break
            for card in job_cards:
                # Extract job ID from the card's data attribute
                try:
                    data_entity = card.find('div', class_='base-card').get('data-entity-urn')
                    job_id = data_entity.split(":")[3] if data_entity else "N/A"
                except Exception as e:
                    logger.debug(f"Failed to extract job ID from card: {e}")
                    continue  # Skip this card if job ID extraction fails

                # Construct a direct job URL using the job ID
                job_url = f"https://hk.linkedin.com/jobs/view/{job_id}"
                
                # Extract other key information (title, company, location, posted date)
                title_tag = card.find('span', class_='sr-only')
                company_tag = card.find('a', class_='hidden-nested-link')
                location_tag = card.find('span', class_='job-search-card__location')
                date_tag = card.find('time', class_='job-search-card__listdate')
                
                title = title_tag.text.strip() if title_tag else "N/A"
                company = company_tag.text.strip() if company_tag else "N/A"
                job_location = location_tag.text.strip() if location_tag else "N/A"
                posted = date_tag.text.strip() if date_tag else "N/A"

                job_info = {
                    "job_id": job_id,
                    "title": title,
                    "company": company,
                    "location": job_location,
                    "posted": posted,
                    "url": job_url
                }
                jobs.append(job_info)
            
            # If no jobs were successfully scraped, log a warning and return a friendly message.
            if not jobs:
                logger.warning("No job postings found or failed to parse any job cards from LinkedIn response.")
                return "No job postings found on LinkedIn."
            
        # Format the job information into a readable string
        job_strs = []
        for idx, job in enumerate(jobs, 1):
            job_str = (
                f"Job #{idx} — ID: {job['job_id']}\n"
                f"Title    : {job['title']}\n"
                f"Company  : {job['company']}\n"
                f"Location : {job['location']}\n"
                f"Posted   : {job['posted']}\n"
                f"URL      : {job['url']}\n"
                f"{'=' * 50}\n"
            )
            job_strs.append(job_str)
        
        formatted_jobs = "\n".join(job_strs)
        logger.info(f"Successfully parsed and formatted {len(jobs)} job listings from LinkedIn.")
        return formatted_jobs
    
    except requests.exceptions.Timeout:
        logger.error(f"Timeout occurred during LinkedIn search for keywords: '{keywords}'.")
        return f"Error: Timeout occurred while searching LinkedIn for '{keywords}'."
    except requests.exceptions.RequestException as e:
        status_code = e.response.status_code if e.response is not None else 'N/A'
        logger.error(f"HTTP error during LinkedIn search: {e} (Status code: {status_code}).")
        return f"Error: Could not connect to LinkedIn (Status: {status_code}) for '{keywords}': {e}"
    except Exception as e:
        logger.error(f"Unexpected error during LinkedIn search for '{keywords}': {e}", exc_info=True)
        return f"Error: An unexpected error occurred during LinkedIn search: {e}"


@tool
def extract_job_details(job_id: str, platform: str) -> str:
    """
    Extracts the full job title and a concise summary of requirements/responsibilities
    for a specific job ID obtained from 'jobsdb_search' or 'linkedin_search'.
    It scrapes the job's detail page and uses an LLM for summarization.
    Use this *after* identifying a promising job ID from search results.
    Note: Scraping detail pages, especially LinkedIn, might fail.

    Args:
        job_id (str): The specific ID of the job (e.g., "JHK100003009123456" for JobsDB, or a numerical ID like "3881234567" for LinkedIn).
        platform (str): The platform the job ID belongs to. Must be 'jobsdb' or 'linkedin'.
    """
    platform = platform.lower()
    logger.info(f"Extracting details for {platform.upper()} job ID: {job_id}")

    if platform == 'jobsdb':
        url = f"https://hk.jobsdb.com/job/{job_id}"
    elif platform == 'linkedin':
        # Construct the standard LinkedIn job view URL
        url = f"https://www.linkedin.com/jobs/view/{job_id}" # Use www, might be more stable for guest view
    else:
        logger.error(f"Invalid platform '{platform}' specified for job ID {job_id}.")
        return "Error: Invalid platform specified. Must be 'jobsdb' or 'linkedin'."

    logger.debug(f"Attempting to scrape job details from URL: {url}")
    text = scrape_all_text_original(url) # Use the robust text scraper

    if text is None or text.startswith("Error:"): # Check if scraping failed or returned an error string
        error_message = f"Error: Unable to scrape content from {url} for {platform.upper()} job ID {job_id}. Cannot extract details. Reason: {text or 'No content returned'}"
        logger.error(error_message)
        # Return the scraping error directly to the agent
        return error_message

    if not text.strip():
         error_message = f"Error: Scraped content from {url} for {platform.upper()} job ID {job_id} was empty. Cannot extract details."
         logger.error(error_message)
         return error_message

    # Limit text size sent to LLM (important for cost and context window)
    max_chars = 18000 # Increased slightly for potentially longer descriptions
    if len(text) > max_chars:
        logger.warning(f"{platform.upper()} job description text long ({len(text)} chars), truncating to {max_chars} for LLM analysis.")
        text_to_send = text[:max_chars] + "\n... [Content Truncated]"
    else:
        text_to_send = text

    # Consistent prompt for extraction
    prompt_extract = f"""
    Given the following text scraped from a job posting page ({platform.upper()}, Job ID: {job_id}) at URL {url}:
    --- START TEXT ---
    {text_to_send}
    --- END TEXT ---

    Analyze the text and extract the following information:
    1.  "title": The full, specific job title mentioned in the posting (e.g., "Senior Software Engineer (Backend, Java)", "Marketing Director - APAC").
    2.  "summary": A concise summary (3-5 sentences) covering the core responsibilities and key requirements (skills, experience level, qualifications). Focus on details relevant for matching with a CV. Highlight any salary information if explicitly stated.

    Return the result ONLY in the following JSON format:
    ```json
    {{
      "title": "...",
      "summary": "..."
    }}
    ```
    If the title or summary cannot be reliably extracted (e.g., page is an error, irrelevant content), use the string "Not Found" as the value. Do not add explanations outside the JSON structure. Check if the text seems like a valid job description before extracting. If it looks like an error page or login prompt, set both fields to "Not Found".
    """
    try:
        logger.debug(f"Invoking LLM for {platform.upper()} job detail extraction (ID: {job_id}).")
        messages = [HumanMessage(content=prompt_extract)]
        response = llm.invoke(messages)
        response_content = response.content.strip()

        logger.debug(f"Raw LLM response for extraction (Job ID: {job_id}):\n{response_content}")

        # Attempt to parse the JSON response (more robustly)
        try:
            # Find JSON block within potential markdown fences or other text
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', response_content, re.DOTALL)
            if json_match:
                json_string = json_match.group(1)
            else:
                 # Fallback: assume the whole response is JSON if no fences found
                 json_string = response_content
                 # Basic check if it looks like JSON
                 if not json_string.startswith('{') or not json_string.endswith('}'):
                     raise json.JSONDecodeError("Response does not appear to be JSON.", json_string, 0)


            # Clean potential escape sequences before parsing
            json_string = json_string.replace('\\n', '\n').replace('\\"', '"')

            details_json = json.loads(json_string)
            title = details_json.get("title", "Extraction Error: Title Key Missing")
            summary = details_json.get("summary", "Extraction Error: Summary Key Missing")

            if title == "Not Found" and summary == "Not Found":
                logger.warning(f"LLM indicated title and summary not found for {platform.upper()} job {job_id} (URL: {url}). Might be error page or invalid content.")
                return f"Platform: {platform.upper()}\nJob ID: {job_id}\nStatus: Could not extract title or summary from the job page content (URL: {url}). Content might be invalid or inaccessible."
            elif title == "Not Found":
                logger.warning(f"LLM indicated title not found for {platform.upper()} job {job_id}.")
                title = "[Title Not Found in Content]" # Use clearer status
            elif summary == "Not Found":
                logger.warning(f"LLM indicated summary not found for {platform.upper()} job {job_id}.")
                summary = "[Summary Not Found in Content]" # Use clearer status


            result_str = (f"Platform: {platform.upper()}\n"
                          f"Job ID  : {job_id}\n"
                          f"Title   : {title}\n"
                          f"Summary : {summary}")
            logger.info(f"Successfully extracted details for {platform.upper()} job ID {job_id}.")
            return result_str

        except json.JSONDecodeError as json_e:
            error_message = f"Error: Failed to parse JSON response from LLM for {platform.upper()} job {job_id}. Raw response: '{response_content}'. Error: {json_e}"
            logger.error(error_message)
            # Fallback: Return raw response if parsing fails, indicating an issue
            return f"Platform: {platform.upper()}\nJob ID: {job_id}\nStatus: Error processing LLM response - JSON parsing failed. Raw output: {response_content}"
        except Exception as parse_e:
            error_message = f"Error: Unexpected error parsing LLM response for {platform.upper()} job {job_id}. Error: {parse_e}"
            logger.error(error_message, exc_info=True)
            return f"Platform: {platform.upper()}\nJob ID: {job_id}\nStatus: Error processing LLM response. Details: {parse_e}"


    except Exception as e:
        # Catch errors during the LLM call itself
        error_message = f"Error: LLM invocation failed during job detail extraction for {platform.upper()} job {job_id}: {e}"
        logger.error(error_message, exc_info=True)
        return error_message

# ---------------- Helper Functions ----------------
def scrape_all_text_original(url: str) -> Optional[str]:
    """
    Scrape and return cleaned TEXT content from the given URL.
    (Uses randomized user-agent, delay, specific headers, specific cleaning logic - Adapt from your original code)
    Returns error message string on failure.
    """
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36 Edg/134.0.3124.95",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36 Edg/135.0.0.0",
    ]
    headers = { # Use headers appropriate for getting content to extract text from
        'User-Agent': random.choice(user_agents),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'en-US,en;q=0.9,en-GB;q=0.8',
        # Add other headers from your original scrape_all_text if they were different
    }
    try:
        delay = random.uniform(1.5, 2.0)
        logger.debug(f"(Original Text Scraper) Scraping URL: {url} (Delay: {delay:.2f}s)")
        time.sleep(delay)
        response = requests.get(url, headers=headers, timeout=25) # Adjust timeout
        response.raise_for_status()

        content_type = response.headers.get('Content-Type', '').lower()
        if 'html' not in content_type:
             logger.warning(f"(Original Text Scraper) Non-HTML content type '{content_type}' received from {url}")
             return f"Error: Received non-HTML content ({content_type}) from {url}"

        soup = BeautifulSoup(response.content, 'html.parser')

        # --- Your Original Cleaning Logic Here ---
        # Example: replicate the cleaning from the *first* version you posted
        for element in soup(["script", "style", "header", "footer", "nav", "aside"]): # Use the exact tags you had
             element.decompose()
        text = soup.get_text(separator='\n', strip=True)
        # Add any other specific cleaning steps you had in the original scrape_all_text
        # -----------------------------------------

        if not text.strip():
             logger.warning(f"(Original Text Scraper) Extracted text from {url} is empty after cleaning.")
             # Add checks for block pages if needed
             return f"Error: Extracted text from {url} is empty."

        logger.debug(f"(Original Text Scraper) Successfully scraped and extracted text from {url} (Length: {len(text)}).")
        return text

    except requests.exceptions.Timeout:
        logger.error(f"(Original Text Scraper) Timeout error fetching URL {url}")
        return f"Error: Timeout occurred while trying to fetch {url}"
    # ... add other specific except blocks from your original scrape_all_text ...
    except requests.exceptions.RequestException as e:
        logger.error(f"(Original Text Scraper) Request error fetching URL {url}: {e}")
        status_code = e.response.status_code if e.response is not None else 'N/A'
        return f"Error: Failed to fetch {url} (Status: {status_code}): {e}"
    except Exception as e:
        logger.error(f"(Original Text Scraper) Unexpected error scraping URL {url}: {e}", exc_info=True)
        return f"Error: An unexpected error occurred during scraping: {e}"


def format_job(job: dict) -> str:
    """Format and return job details from a JobsDB job dictionary."""
    # Adapt based on actual JobsDB API response structure observed
    title = job.get("title", "N/A")
    company_data = job.get("companyMeta", {}) # Look in companyMeta
    company = company_data.get("name", job.get("companyName", "N/A")) # Fallback to companyName

    advertiser_data = job.get("advertiser", {})
    advertiser = advertiser_data.get("description", "N/A") if advertiser_data else "N/A"

    jobsdb_id = job.get("id", "N/A")
    locations_data = job.get("locationHierarchy", {}) # Use locationHierarchy
    # Combine location levels if they exist
    locations = ", ".join(filter(None, [
        locations_data.get("country", {}).get("name"),
        locations_data.get("state", {}).get("name"),
        locations_data.get("city", {}).get("name"),
        locations_data.get("area", {}).get("name")
    ])) or "N/A"

    # Handle potentially complex salary structures
    salary_data = job.get("salary", {})
    if isinstance(salary_data, dict):
        salary_text = salary_data.get("label", {}).get("text") # Prefer label text
        if not salary_text:
             # Fallback to constructing from min/max/type if label missing
             min_sal = salary_data.get("min")
             max_sal = salary_data.get("max")
             sal_type = salary_data.get("type")
             if min_sal and max_sal and sal_type:
                 salary_text = f"{min_sal:,} - {max_sal:,} ({sal_type})"
             elif min_sal and sal_type:
                  salary_text = f"From {min_sal:,} ({sal_type})"
             elif sal_type:
                  salary_text = f"Salary Type: {sal_type}"
             else:
                 salary_text = "Not Specified"
        salary = salary_text
    elif isinstance(salary_data, str): # Handle simple string salary
        salary = salary_data
    else:
        salary = "Not Specified"

    bullet_points = job.get("bulletPoints", [])
    teaser = job.get("teaser", "")
    classification = job.get("classification", {}).get("description", "N/A") # Job function/category


    formatted = (
        f"Platform       : JobsDB\n" # Add platform marker
        f"Job ID         : {jobsdb_id}\n"
        f"Title          : {title}\n"
        f"Company        : {company}\n"
        f"Advertiser     : {advertiser}\n"
        f"Location(s)    : {locations}\n"
        f"Salary         : {salary}\n"
        f"Classification : {classification}\n"
        f"Teaser         : {teaser}\n"
        f"Highlights     :\n"
    )
    if bullet_points:
        for bp in bullet_points:
            formatted += f"  - {bp}\n"
    else:
        formatted += "  N/A\n"
    # Add other potentially useful fields if needed (work type, etc.)
    return formatted

def read_cv(cv_file_path: str) -> Optional[str]:
    """Read and return the content of a .docx file (CV)."""
    if not os.path.exists(cv_file_path):
        logger.error(f"CV file not found at {cv_file_path}")
        return None # Indicate file not found
    if not cv_file_path.lower().endswith(".docx"):
       logger.error(f"Invalid file type. Only .docx files are supported. Path: {cv_file_path}")
       return None # Indicate wrong file type
    try:
        logger.info(f"Reading CV file from {cv_file_path}")
        loader = Docx2txtLoader(cv_file_path)
        docs = loader.load()
        if not docs:
            logger.warning(f"No content extracted from CV file: {cv_file_path}")
            return "" # Return empty string if no content

        content = "\n".join(d.page_content for d in docs if hasattr(d, 'page_content'))
        logger.info(f"Successfully read CV file (Length: {len(content)}).")
        return content
    except Exception as e:
        logger.error(f"Error reading CV file {cv_file_path}: {e}", exc_info=True)
        return None # Indicate reading error


# ---------------- Agent and Executor Initialization ----------------
def search(api_key: str, cv_content: str) -> str:
    """
    Main function to search for jobs using the agent with the provided API key and CV content.
    This function is a placeholder and should be replaced with the actual logic to invoke the agent.
    """
    # ---------------- Prompt Template ----------------
    # Updated prompt to incorporate LinkedIn, better search strategy, company focus
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """
                You are an expert Recruitment Assistant specializing in the Hong Kong job market (but adaptable to other locations if specified).
                Your goal is to find the ***top 5 best*** job matches for the user based on their provided CV and any stated preferences, ordered from best fit to fifth best fit.
                Remember, the goal is to find high-quality matches, which often requires a reasonably broad search of the job market. Therefore, proactively consider using both available platforms (JobsDB and LinkedIn) during your search phase.

                Follow these steps methodically:

                1.  **Analyze CV:** Thoroughly review the user's CV. Identify:
                    * Key skills (technical, soft, domain-specific).
                    * Years of relevant experience and seniority level.
                    * Primary job functions and roles held.
                    * Industries worked in.
                    * Educational background.
                    * Any explicitly stated career goals, location preferences, or salary expectations.

                2.  **Develop Initial Search Strategy:** Based on the CV analysis, determine the most promising initial search approach:
                    * Identify 1-2 core job titles or functions (e.g., 'Software Engineer', 'Project Manager', 'Data Analyst').
                    * List relevant keywords (e.g., 'Python', 'React', 'AWS', 'Agile', 'Financial Reporting', 'Stakeholder Management').
                    * Consider the target location (default to Hong Kong unless specified otherwise).
                    * Plan to search *both* JobsDB (`jobsdb_search`) and LinkedIn (`linkedin_search`) to ensure broad market coverage. Even if you might *start* with one platform based on the profile (e.g., JobsDB for local roles, LinkedIn for tech/multinational), include using the other as well especially if the first search isn't highly successful.
                    * Consider if adding company names (e.g., 'Google', 'HSBC') or types (e.g., 'big tech', 'fintech startup', 'investment bank') to the keywords is relevant based on the CV or user request.

                3.  **Execute Initial Search:** Use the *first chosen* tool (`jobsdb_search` or `linkedin_search`) with the identified keywords, location, and `page=1`.
                    * **Important for LinkedIn:** Remember that LinkedIn search only accepts **2 to 3 keywords**. If your initial keyword set for LinkedIn yields no results, refine your keyword list by selecting only the most critical or high-impact terms from the CV and user preferences before reattempting the search.

                4.  **Evaluate Initial Results:** Examine the job summaries returned.
                    * Are they relevant to the user's profile (title, seniority, industry)?
                    * Do any descriptions look promising?
                    * Are there enough potential candidates (aim for more than 5 initially)? Are they diverse enough?
                    * Note down the Job IDs and Platforms of *at least 5-7 promising* candidates to allow for filtering and ranking later. Keep in mind that LinkedIn results may be less reliable, so be cautious if extraction issues arise.

                5.  **Refine Search Strategy (Iterative Process - CRITICAL):**
                    * **If results are poor, insufficient (fewer than 5-7 promising leads), OR if the second platform hasn't been tried yet and might offer better options:** *Think step-by-step* about why and how to improve or broaden the search. DO NOT give up after only one platform search unless results were perfect and plentiful.
                    * **Consider:**
                        * **Adjusting Keywords:** Use broader terms, more specific skills, synonyms, different job titles, or adding company names/types if necessary.
                            * For LinkedIn, ensure that your revised keyword list still adheres to the 2 to 3 keyword rule. If the revised search on LinkedIn still fails to produce results, further narrow and focus the keywords.
                        * **Adding/Switching Platforms:** If the first platform searched (e.g., JobsDB) did not yield highly satisfactory results or sufficient diversity/quantity of options, ensure you also search the *other* platform (e.g., LinkedIn) using the appropriate keywords. Even if the first search found *some* results, consider if searching the second platform could yield *better* or *more* matches. Clearly explain why you are adding or switching platforms.
                        * **Trying More Pages:** If results look acceptable but limited, try using `page=2` or `page=3` on the same platform with the same keywords.
                        * **Revising Location:** Confirm that the location settings are correct.
                    * **Explain your reasoning:** Briefly state *why* you are changing the search strategy or adding an additional platform search.
                    * **Execute Refined Search:** Use the appropriate tool with the newly refined parameters.
                    * **Evaluate Again:** Assess the new results. Repeat the refinement process if necessary (up to 2-3 refinement cycles across both platforms). Aim to gather a pool of strong candidates.
                    * **If multiple attempts fail:** After strategic search attempts across both platforms, if fewer than 5 promising candidates are found, clearly state this and proceed with the ones you have.

                6.  **Extract Details:** Once you have identified your pool of the most promising Job IDs (aiming for 5-7 initially), use the `extract_job_details` tool one by one for each ID, ensuring you specify the correct platform ('jobsdb' or 'linkedin'). Prepare for potential extraction failures, particularly on LinkedIn; if a specific job's extraction fails, note it and consider using the search summary or discarding the candidate if the data is too vague to rank properly.

                7.  **Compare, Analyze, and Rank:** Critically compare the extracted details (job title, summary, requirements, company culture if available, etc.) of the viable candidate jobs against the user's CV.
                    * Evaluate the match for skills, experience level, responsibilities, industry, and any user preferences (salary, location, company type).
                    * Identify the strengths of the match and any potential gaps for each job.
                    * Consider salary alignment if such details are available.
                    * Based on this comprehensive analysis, **rank the jobs from 1 (best fit) to 5 (fifth best fit)**. Discard candidates that are clearly poorer fits than your top 5 after detailed review.

                8.  **Final Output (Top 5 Jobs - JSON Format):**
                    * Present the top 5 jobs you identified and ranked in a **JSON format**.
                    * The JSON output should be a list of objects, where each object represents a job.
                    * Each job object *must* contain the following keys:
                        * `Rank`: (Integer) The rank of the job match (1 to 5).
                        * `JobID`: (String) The Job ID from the platform.
                        * `Platform`: (String) The platform where the job was found (e.g., "JobsDB", "LinkedIn").
                        * `JobTitle`: (String) The full job title.
                        * `Company`: (String) The name of the hiring company (use the client company name if it's a recruitment agency post and the client is specified, otherwise use the agency name). Include "(recruitment agency)" or similar if appropriate and known. Use `null` or omit if not available.
                        * `Explanation`: (String) A clear explanation (2-4 sentences) summarizing why this specific job is a good fit for the user's profile and justifies its rank, referencing specific CV points and job requirements/details.
                    * **Example JSON Structure:**
                        ```json
                        [
                        {{
                            "Rank": 1,
                            "JobID": "...",
                            "Platform": "JobsDB",
                            "JobTitle": "Senior Full Stack Developer (Node.js + Python)",
                            "Company": "Nicoll Curtin Technology (Client: [Client Company Name])",
                            "Explanation": "Excellent match due to strong Node.js/Python skills listed on CV, aligns with 3 years experience for Senior level. Relevant full-stack project experience compensates for lack of explicit payment systems background mentioned as a plus."
                        }},
                        {{
                            "Rank": 2,
                            "JobID": "...",
                            "Platform": "LinkedIn",
                            "JobTitle": "Software Engineer - Backend",
                            "Company": "Tech Solutions Inc.",
                            "Explanation": "Good fit focusing on Python backend skills. Seniority matches experience level. Lacks the full-stack element but strong alignment on core tech stack."
                        }},
                        // ... up to 3 more job objects
                        ]
                        ```
                    * **Handling Fewer Results:** If, after diligent searching and analysis (ideally including both platforms), you find fewer than 5 suitable jobs, present only those found in the JSON list, ranked accordingly (e.g., if only 3 are found, rank them 1, 2, 3).
                    * **Handling No Results:** If no suitable jobs are found, return an empty JSON list (`[]`).

                Remember:
                - You MUST use the available tools to search for and analyze jobs. Do not invent job details.
                - If scraping or extraction fails for a tool, report the error and adjust your strategy (e.g., try another candidate, rely on summary data if sufficient, or reduce the final number of jobs).
                - Always prioritize finding high-quality matches based on deep analysis.
                """ 
            ),
            MessagesPlaceholder(variable_name="chat_history", optional=True),
            ("human", "{input}"), # User query + CV content
            MessagesPlaceholder(variable_name="agent_scratchpad"), # Agent's work
        ]
    )

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.0-flash-001",
        temperature=0,
        max_tokens=None,
        timeout=None,
        max_retries=3,
        google_api_key=api_key,
        # other params...
    )
    # Define the tools the agent can use
    tools = [jobsdb_search, linkedin_search, extract_job_details] # Add linkedin_search

    # Create the agent
    # Ensure the LLM supports tool calling (OpenAI models generally do)
    agent = create_openai_tools_agent(llm, tools, prompt)

    # Create the AgentExecutor
    agent_executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True, # Set True to see thought process, False for cleaner output
        handle_parsing_errors="Check your output and make sure it conforms!", # Provide specific guidance on parsing errors
        max_iterations=15, # Allow more steps for refinement
        # Early stopping can be added if needed, e.g., based on finding a good match
        # return_intermediate_steps=True # Set True to see tool calls/outputs separately
    )
    logger.info("Agent and Executor initialized with JobsDB and LinkedIn tools.")
    if cv_content is None:
        logger.critical("Failed to read CV content. Please check the file path and format (.docx). Exiting.")
        exit(1)
    elif not cv_content.strip():
        logger.warning(f"CV file '{cv_path}' was read but appears to be empty or contains only whitespace.")
        # Depending on use case, you might allow running without a CV, but this agent relies heavily on it.
        logger.critical("CV content is empty. Agent requires CV details to function effectively. Exiting.")
        exit(1)

    # Structure the input clearly for the agent
    initial_query_with_cv = f"""
    # User Request: Please find the best job match for me in Hong Kong based on my CV. Analyze my skills and experience carefully. Consider roles from both JobsDB and LinkedIn. If initial searches aren't great, try refining keywords or switching platforms. Focus on roles in established tech companies or high-growth startups if relevant based on my profile.

    # My CV Content:
    # --- START CV ---
    # {cv_content}
    # --- END CV ---
    # """

    logger.info("Invoking the agent executor...")
    start_time = time.time()
    try:
        # Input must be a dictionary with keys matching the prompt variables
        response = agent_executor.invoke({"input": initial_query_with_cv})
        end_time = time.time()
        logger.info(f"Agent execution finished in {end_time - start_time:.2f} seconds.")

        # The final answer from the agent is typically in the 'output' key
        final_answer = response.get("output", "Agent did not produce a final output.")

        return final_answer

    except Exception as e:
        end_time = time.time()
        # Log the full exception traceback for debugging
        logger.critical(f"An error occurred during agent execution after {end_time - start_time:.2f} seconds: {e}", exc_info=True)
        print(f"\nAn critical error occurred during agent execution: {e}")
        print("Please check the logs for more details.")

if __name__ == "__main__":
    cv_path = "TestCV.docx"
    search('API_KEY', read_cv(cv_file_path=cv_path))
