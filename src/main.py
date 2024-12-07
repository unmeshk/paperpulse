import os
import openai
import pickle

import urllib.request as libreq
import time
from datetime import datetime, date, timedelta, timezone
import xml.etree.ElementTree as ET

# Initialize lists to store paper information and URLs
paper_info_list = []
paper_url_list = []

# Define the search query and sorting parameters
SEARCH_QUERY = 'cat:cs.LG'
SORT_BY = 'lastUpdatedDate'
SORT_ORDER = 'descending'


def identify_important_papers(paper_info_list):
    """Calls the OpenAI API to identify important papers."""
    # Set up the OpenAI API key
    openai.api_key = os.getenv("OPENAI_API_KEY")  

    # Construct the prompt
    prompt_summary = (
        """
        You are a research scientist and professor with a PhD in machine learning. 
        You are also an educator skilled in explaining complex scientific concepts to
        the average technology professional. Your summaries and explanations of concepts
        and papers in machine learning and artificial intelligence are like
        how Neil Degrasse Tyson and Carl Sagan explain astronomy and cosmology concepts. 
        Read through the titles and abstracts of these machine learning papers and write a 1000 to 5000 word 
        summary of the important findings from these papers. Separate these findings into themes to make it easier to read. 
        \n\n
        PAPERS AND SUMMARIES \n
        """
        + "\n".join(paper_info_list)
    )

    prompt_papers = (
        """
        You are a research scientist and professor with a PhD in machine learning. 
        You are skilled at identifying important advancements in AI and machine learning.
        Read through the titles and abstracts of these machine learning papers and identify the 10 most important 
        papers in terms of contributions to the field of AI and machine learning.
        \n\n
        PAPERS AND SUMMARIES \n
        """
        + "\n".join(paper_info_list)
    )

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
    papers = response.choices[0].message.content

    return summaries,papers

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



def retrieve_daily_results(search_query, sort_by, sort_order):
    """
    Retrieves all result for the last day.
    Retrieves results 10 at a time, starting from a week ago and continuing
    till the latest paper is retrieved. 
    """

    # Define the desired timezone - using UTC for consistency
    desired_timezone = timezone.utc 

    # Calculate the date one week ago in the desired timezone
    #currdate = datetime.now(desired_timezone)
    #print(f'Current datetime: {currdate}')
    #one_day_ago = currdate - timedelta(days=1)
    #print(f'Retrieving results for {one_day_ago}')
    one_day_ago = None

    start = 0
    max_results = 10  # You can adjust this if needed, but stay within API limits

    while True:
        url = f'http://export.arxiv.org/api/query?search_query={search_query}&sortBy={sort_by}&sortOrder={sort_order}&start={start}&max_results={max_results}'
        #print(url)
        
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

                if not one_day_ago:
                    one_day_ago = updated_date - timedelta(days=1)
                    print(f'Retrieving papers for: {one_day_ago}')
                
                if updated_date > one_day_ago:
                    process_data(entry)
                else:
                    # Stop processing since entries are sorted by last updated date
                    break

        # Increment start index for the next batch
        start += max_results
        print(f'latest date: {updated_date}')
        time.sleep(5)
        if start>400: # never retrieve more than 400 results
            break

def main():
    """Main function to orchestrate the retrieval process."""
    
    #retrieve_daily_results(SEARCH_QUERY, SORT_BY, SORT_ORDER)
    

    # write the retrieved stuff to file temporarily to 
    # reuse so that we don't call the API frequently. 
    #with open("paperinfo.pkl", "wb") as file:  
    #    pickle.dump(paper_info_list, file)
    #with open("paperurls.pkl", "wb") as file:  
    #    pickle.dump(paper_url_list, file)
    with open('paperinfo.pkl', 'rb') as file:  # Open in read-binary mode
        paper_info_list = pickle.load(file)
    with open('paperinfo.pkl', 'rb') as file:  # Open in read-binary mode
        paper_url_list = pickle.load(file)
    
    print(f'Number retrieved: {len(paper_info_list)}')

    res,paps = identify_important_papers(paper_info_list)
    print(res)
    print(paps)
    #print(paper_url_list)

    # write the res and paps files
    with open("summaries.txt", "w") as file:  # 'wb' means write binary
        file.write(res)
    with open("papers.txt", "w") as file:  # 'wb' means write binary
        file.write(paps)

    # add the url back to the titles of these papers

    # Write to a webpage. Put in backend.
    

if __name__ == "__main__":
    main()

    #important_titles = identify_important_papers(paper_info_list)
    #print("Important Paper Titles:", important_titles)