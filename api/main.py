import os
import openai
import pickle
import re
import logging

import urllib
import urllib.request as libreq
import time
from datetime import datetime, date, timedelta, timezone
import xml.etree.ElementTree as ET

from dotenv import load_dotenv
from api.utils import (
    extract_text_from_pdf, 
    extract_images_from_pdf_base64,
    download_pdf,
    add_markdown_links
    )
from api.settings import SUMMARY_PROMPT, TOP5_PAPERS_PROMPT
from api.webs import create_blogpost
from api.agent import summarize_paper

# Load the .env file
load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(filename='myapp.log', level=logging.INFO)


# Initialize lists to store paper information and URLs
papers = []

# Define the search query and sorting parameters
SEARCH_QUERY = 'cat:cs.LG+OR+cat:cs.AI+OR+cat:cs.CL+OR+cat:cs.CV'
SORT_BY = 'lastUpdatedDate'
SORT_ORDER = 'descending'

#open ai api
openai.api_key = os.getenv("OPENAI_API_KEY")

def combine_paper_info(paper):
    """
    Combines the title, authors, and summary into a single string

    Args:
    paper: the dict containing details of the paper
    """
    return f"**Title:** {paper['title']}\n**Authors:** {', '.join(paper['authors'])}\n**Summary:** {paper['summary']}\n"

def identify_important_papers(papers):
    """
    Calls the OpenAI API to identify important papers.
    
    Args:
        papers (list): list of dicts each containing information about one paper

    Returns:
        summaries (string): summary of all the papers in papers
        papers (string): Top 10 papers from the list of papers
    """

    combined_paper_info = "\n".join(combine_paper_info(p) for p in papers)
      
    # Construct the prompt
    prompt_summary = SUMMARY_PROMPT + combined_paper_info

    # get summaries
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": prompt_summary}
    ]

    # Call the OpenAI API
    response = openai.chat.completions.create(
        model="gpt-4o-mini", 
        messages=messages,
        max_tokens=5000, 
        temperature=0.1,
        top_p=0.9,  # Adjust as needed
    )

    # Extract the paper titles from the response
    summaries = response.choices[0].message.content

    # Get the top 5 most important papers in this list
    prompt_papers = TOP5_PAPERS_PROMPT + combined_paper_info

    # get papers
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": prompt_papers}
    ]

    # Call the OpenAI API
    response = openai.chat.completions.create(
        model="gpt-4o-mini", 
        messages=messages,
        max_tokens=5000, 
        temperature=0.1,
        top_p=0.9,  # Adjust as needed
    )

    # Extract the paper titles from the response
    top5_papers = response.choices[0].message.content

    return summaries, top5_papers


def process_data(entry):
    """
    Parses the data retrieved by the ArXiV API call, extracts information, and populates a dict

    Args:   
        entry: an XML string

    Returns:
        dict: containing the parsed values
    """
    affiliations = []
    paper = {}
    paper['title'] = entry.find('{http://www.w3.org/2005/Atom}title').text
    paper['authors'] = [author.find('{http://www.w3.org/2005/Atom}name').text 
                for author in entry.findall('{http://www.w3.org/2005/Atom}author')]
    for author in entry.findall('{http://www.w3.org/2005/Atom}author'):
        affiliation_element = author.find('{http://arxiv.org/schemas/atom}affiliation')
        if affiliation_element is not None:
            affiliations.append(affiliation_element.text)
    paper['summary'] = entry.find('{http://www.w3.org/2005/Atom}summary').text
    paper['url'] = entry.find('{http://www.w3.org/2005/Atom}id').text

    return paper

def retrieve_daily_results(search_query, sort_by, sort_order):
    """
    Retrieves all result for the last day.
    Retrieves results 10 at a time, starting from a week ago and continuing
    till the latest paper is retrieved. 

    Args:
        search_query (string): the exact query being searched for on ArXiV
        sort_by (string): what to sort by like the last updated date
        sort_order (string): descending or ascending

    Returns:
        list: list of dicts (title, authors, summary, url) of parsed information about papers.
    """
    papers = []
    # Define the desired timezone - using UTC for consistency
    desired_timezone = timezone.utc 

    # Calculate the date one week ago in the desired timezone
    #currdate = datetime.now(desired_timezone)
    #print(f'Current datetime: {currdate}')
    #one_day_ago = currdate - timedelta(days=1)
    #print(f'Retrieving results for {one_day_ago}')
    one_day_ago = None

    start = 0
    max_results = 50  

    while True:
        url = f'http://export.arxiv.org/api/query?search_query={search_query}&sortBy={sort_by}&sortOrder={sort_order}&start={start}&max_results={max_results}'
        #print(url)
        
        with libreq.urlopen(url) as response:
            data = response.read()
            root = ET.fromstring(data)

            # Check if any entries were returned
            if len(root.findall('{http://www.w3.org/2005/Atom}entry')) == 0:
                print("No data in returned XML")
                xml_str = ET.tostring(root, encoding='unicode', method='xml')
                print(f'Full xml = {xml_str}')
                break

            for entry in root.findall('{http://www.w3.org/2005/Atom}entry'):
                updated_date_str = entry.find('{http://www.w3.org/2005/Atom}updated').text
                #print(updated_date_str)
                updated_date = datetime.strptime(updated_date_str, '%Y-%m-%dT%H:%M:%S%z')

                # Make sure updated_date is in the desired timezone
                updated_date = updated_date.astimezone(desired_timezone) 

                if not one_day_ago:
                    one_day_ago = updated_date - timedelta(days=1)
                    print(f'Retrieving new/updated papers till : {one_day_ago}')
                
                if updated_date > one_day_ago:
                    papers.append(process_data(entry))
                else:
                    # Stop processing since entries are sorted by last updated date
                    print(f'Current: {updated_date}. Up to: {one_day_ago}')
                    break

        # Increment start index for the next batch
        start += max_results
        print(f'latest date: {updated_date}')
        time.sleep(10)
        if start>1200: # never retrieve more than 400 results
            print('Found more than 1200 papers')
            break
    
    return papers

    
    
def extract_titles(content):
    """
    Extracts titles from the content using regex.
    
    Titles are assumed to follow the pattern:
    - A number followed by a period (`1.`, `2.`, etc.)
    - The title is enclosed in double asterisks (`**`).
    
    Args:
        content (str): The string content containing the top 5 papers selected by the LLM.
    
    Returns:
        list: A list of titles extracted from the content.
    """
    # Match lines starting with a number followed by a title in double asterisks
    matches = re.findall(r"\d+\.\s\*\*(.*?)\*\*", content)
    return matches

def filter_dicts_by_titles(dict_list, titles):
    """
    Filters the dictionaries in the input list by matching titles,
    ignoring special characters and whitespace differences.

    Args:
        dict_list (list): A list of dictionaries, each containing a 'title' key.
        titles (list): A list of titles extracted from the content.

    Returns:
        list: Filtered dictionaries that match the titles.
    """
    def normalize(text):
        # Remove special characters and extra whitespace
        return re.sub(r'\s+', ' ', text.strip()).replace('\n', '')

    # Normalize extracted titles for comparison
    normalized_titles = [normalize(title) for title in titles]

    # Filter dictionaries whose normalized title matches any in the normalized titles
    return [item for item in dict_list if normalize(item.get('title', '')) in normalized_titles]

    

def get_pdf_url(arxiv_url):
    """
    Extracts the PDF URL from an arXiv abstract page URL using the arXiv API.

    Args:
        arxiv_url (str): The URL of the arXiv abstract page.

    Returns:
        str: The URL of the PDF, or None if not found.
    """

    # 1. Extract the arXiv ID from the URL
    match = re.search(r'abs/([\w\.\/]+)', arxiv_url)
    if not match:
        return None
    arxiv_id = match.group(1)

    # 2. Construct the API query URL
    api_url = f'http://export.arxiv.org/api/query?id_list={arxiv_id}'

    try:
        # 3. Call the API and get the Atom feed
        with libreq.urlopen(api_url) as response:
             xml_content = response.read()

        # 4. Parse the Atom feed
        tree = ET.fromstring(xml_content)

        # Register the namespaces
        namespaces = {
            'atom': 'http://www.w3.org/2005/Atom',
            'arxiv': 'http://arxiv.org/schemas/atom'
        }

        # 5. Find the PDF link
        for entry in tree.findall('atom:entry', namespaces):
            for link in entry.findall('atom:link', namespaces):
                if link.get('rel') == 'related' and link.get('title') == 'pdf':
                    return link.get('href')
        return None


    except urllib.error.URLError as e:
        logger.error(f"Error: Could not retrieve data from the API. {e}")
        return None
    except ET.ParseError as e:
        logger.error(f"Error: Could not parse the XML data. {e}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred {e}")
        return None


def main():
    """
    Main function to orchestrate the retrieval process.
    """

    try:
        logger.info('Retrieving daily results')
        papers = retrieve_daily_results(SEARCH_QUERY, SORT_BY, SORT_ORDER)
        
        # write the retrieved stuff to file temporarily to 
        # reuse so that we don't call the API frequently. 
        #with open("papers.pkl", "wb") as file:  
        #    pickle.dump(papers, file)
        #with open('papers.pkl', 'rb') as file:  # Open in read-binary mode
        #    papers = pickle.load(file)
        
        if not papers:
            print('No papers retrieved')
            return
        
        logger.info(f'Retrieved: {len(papers)} papers')

        summary,top5 = identify_important_papers(papers)
    except Exception as e:
        print(f'Exception: {e.message}')

    #logger.info(f'Identified the following top 5\n{top5}')
    

    # write the res and paps files
    #with open("summary.txt", "w") as file:  
    #    file.write(summary)
    #with open("top5papers.txt", "w") as file:  
    #    file.write(top5)
    #with open("top5paper-urls.txt", "w") as file:  
    #    file.write(top5)
    #with open("summary.txt", "r") as file:  
    #    summary = file.read()
    #with open("papers.txt", "r") as file:  
    #    top5 = file.read()

    #print(summary)
    #print(top5)

    # map the top5 papers back to the dicts
    #top5_titles = extract_titles(top5)
    #logger.info(f'Extracted the following titles: {top5_titles}')

    # download the entirety of these top5 papers
    #top5_dicts = filter_dicts_by_titles(papers,top5_titles)
    #for paper in top5_dicts:
        #pdf_url = top5_dicts[0]['url'].replace("/abs/", "/pdf/")
        #pdf_file = download_pdf(pdf_url,'pdf_file1.pdf')
        #pdf_file = '/tmp/pdf_file1.pdf'
        
        # use chatgpt to summarize the paper including why it is important, quick summary of the results, and highlight the important papers.
        #paper_summary = summarize_paper(pdf_file)
    #with open("file1_narrative.txt", "w") as file:  
    #    file.write(paper_summary)

    summary_linked = add_markdown_links(summary, papers)
    # write the smummary to a web page based on the day when the papers were retrieved
    create_blogpost(summary_linked, len(papers))


if __name__ == "__main__":
    main()

    #important_titles = identify_important_papers(paper_info_list)
    #print("Important Paper Titles:", important_titles)
