import os
import openai

import urllib.request as libreq
import time
from datetime import datetime, date, timedelta, timezone
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

def process_data(entry):
    """Parses the retrieved data, extracts information, and populates the lists."""
    
    title = entry.find('{http://www.w3.org/2005/Atom}title').text
    authors = [author.find('{http://www.w3.org/2005/Atom}name').text 
                for author in entry.findall('{http://www.w3.org/2005/Atom}author')]
    summary = entry.find('{http://www.w3.org/2005/Atom}summary').text
    url = entry.find('{http://www.w3.org/2005/Atom}id').text

    combined_info = f"**Title:** {title}\n**Authors:** {', '.join(authors)}\n**Summary:** {summary}\n"
    paper_info_list.append(combined_info)
    paper_url_list.append(url)



def retrieve_weekly_results(search_query, sort_by, sort_order):
    """
    Retrieves all result for the last week.
    Retrieves results 10 at a time, starting from a week ago and continuing
    till the latest paper is retrieved. 
    """

    # Define the desired timezone - using UTC for consistency
    desired_timezone = timezone.utc 

    # Calculate the date one week ago in the desired timezone
    one_week_ago = datetime.now(desired_timezone) - timedelta(days=7)

    start = 0
    max_results = 10  # You can adjust this if needed, but stay within API limits

    while True:
        url = f'http://export.arxiv.org/api/query?search_query={search_query}&sortBy={sort_by}&sortOrder={sort_order}&start={start}&max_results={max_results}'
        print(url)
        
        with libreq.urlopen(url) as response:
            data = response.read()
            root = ET.fromstring(data)

            # Check if any entries were returned
            if len(root.findall('{http://www.w3.org/2005/Atom}entry')) == 0:
                break

            for entry in root.findall('{http://www.w3.org/2005/Atom}entry'):
                updated_date_str = entry.find('{http://www.w3.org/2005/Atom}updated').text
                updated_date = datetime.strptime(updated_date_str, '%Y-%m-%dT%H:%M:%S%z')

                # Make sure updated_date is in the desired timezone
                updated_date = updated_date.astimezone(desired_timezone) 


                if updated_date >= one_week_ago:
                    process_data(entry)
                else:
                    # Stop processing since entries are sorted by last updated date
                    break

        # Increment start index for the next batch
        start += max_results
        print(f'latest date: {updated_date}')
        time.sleep(5)
        if start>400:
            break
    

def main():
    """Main function to orchestrate the retrieval process."""
    
    retrieve_weekly_results(SEARCH_QUERY, SORT_BY, SORT_ORDER)

    print(f'Number retrieved: {len(paper_info_list)}')

    

if __name__ == "__main__":
    main()

    #important_titles = identify_important_papers(paper_info_list)
    #print("Important Paper Titles:", important_titles)