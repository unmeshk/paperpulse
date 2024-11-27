import os
import openai

import urllib.request as libreq
import time
from datetime import date, timedelta
import xml.etree.ElementTree as ET

# Initialize lists to store paper information and URLs
paper_info_list = []
paper_url_list = []

# Define the search query and sorting parameters
SEARCH_QUERY = 'cat:cs.LG+OR+cat:cs.AI'
SORT_BY = 'lastUpdatedDate'
SORT_ORDER = 'descending'


def identify_important_papers(paper_info_list):
    """Calls the OpenAI API to identify important papers."""
    # Set up the OpenAI API key
    openai.api_key = os.getenv("OPENAI_API_KEY")  # Replace with your actual API key

    # Construct the prompt
    prompt = (
        "Read through the summaries of these machine learning papers, "
        "identify the important papers, and return the paper titles.\n\n"
        + "\n".join(paper_info_list)
    )

    # Call the OpenAI API
    response = openai.Completion.create(
        engine="text-davinci-003",  # Replace with the actual engine name
        prompt=prompt,
        max_tokens=1000,  # Adjust as needed
        temperature=0.5,  # Adjust as needed
    )

    # Extract the paper titles from the response
    important_paper_titles = response.choices.text.strip().split("\n")

    return important_paper_titles

def process_data(data):
    """Parses the retrieved data, extracts information, and populates the lists."""
    
    root = ET.fromstring(data)
    entries = root.findall('{http://www.w3.org/2005/Atom}entry')
    for entry in entries:
        title = entry.find('{http://www.w3.org/2005/Atom}title').text
        authors = [author.find('{http://www.w3.org/2005/Atom}name').text 
                   for author in entry.findall('{http://www.w3.org/2005/Atom}author')]
        summary = entry.find('{http://www.w3.org/2005/Atom}summary').text
        url = entry.find('{http://www.w3.org/2005/Atom}id').text

        combined_info = f"**Title:** {title}\n**Authors:** {', '.join(authors)}\n**Summary:** {summary}\n"
        paper_info_list.append(combined_info)
        paper_url_list.append(url)


def fetch_arxiv_data(search_query, sort_by, sort_order, start, max_results):
    """Fetches data from the arXiv API."""
    url = f'http://export.arxiv.org/api/query?search_query={search_query}&sortBy={sort_by}&sortOrder={sort_order}&start={start}&max_results={max_results}'
    print(url)
    with libreq.urlopen(url) as response:
        data = response.read()
    return data

def parse_total_results(data):
    """Parses the XML data to extract the total number of results."""
    root = ET.fromstring(data)
    return int(root.find('{http://a9.com/-/spec/opensearch/1.1/}totalResults').text)

def retrieve_daily_results(search_query, sort_by, sort_order, current_date):
    """Retrieves all results for a given day."""
    start = 0
    max_results = 10  # You can adjust this if needed, but stay within API limits
    data = fetch_arxiv_data(search_query, sort_by, sort_order, start, max_results)
    total_results = parse_total_results(data)
    print(f'Total results: {total_results}')
    while start < total_results:
        data = fetch_arxiv_data(search_query, sort_by, sort_order, start, max_results)
        process_data(data)
        start += max_results
        time.sleep(3)  # Wait to avoid overloading the API

def main():
    """Main function to orchestrate the retrieval process."""
    today = date.today()
    one_week_ago = today - timedelta(days=7)
    current_date = one_week_ago
    while current_date <= today:
        print(f'Retrieving papers from {current_date}')
        retrieve_daily_results(SEARCH_QUERY, SORT_BY, SORT_ORDER, current_date)
        current_date += timedelta(days=1)

    print(paper_info_list)

    

if __name__ == "__main__":
    main()

    #important_titles = identify_important_papers(paper_info_list)
    #print("Important Paper Titles:", important_titles)