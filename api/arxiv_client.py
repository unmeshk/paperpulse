import time
import logging
import re
import urllib
import urllib.request as libreq

import xml.etree.ElementTree as ET

from datetime import datetime, date, timedelta, timezone

logger = logging.getLogger(__name__)

class ArxivClient:
    def __init__(self, 
                 search_query='cat:cs.LG+OR+cat:cs.AI+OR+cat:cs.CL+OR+cat:cs.CV',
                 sort_by='lastUpdatedDate',
                 sort_order='descending'):
        
        # Define the search query and sorting parameters
        self.search_query = search_query
        self.sort_by = sort_by
        self.sort_order = sort_order

    def _process_paper_entry(self, entry):
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

    def retrieve_daily_results(self):
        """
        Retrieves all result for the last day.
        Retrieves results 10 at a time, starting from a week ago and continuing
        till the latest paper is retrieved. 

        Args:
            None

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
        max_retries = 3 # sometimes the API fails, so retry 3 times and only then give up.

        while True:
            url = f'http://export.arxiv.org/api/query?search_query={self.search_query}&sortBy={self.sort_by}&sortOrder={self.sort_order}&start={start}&max_results={max_results}'
            
            retry_count = 0
            while retry_count < max_retries:
                try:
                    with libreq.urlopen(url) as response:
                        data = response.read()
                        root = ET.fromstring(data)

                        # Check if any entries were returned
                        if len(root.findall('{http://www.w3.org/2005/Atom}entry')) == 0:
                            retry_count += 1
                            if retry_count == max_retries:
                                print(f"No data in returned XML after {max_retries} attempts")
                                xml_str = ET.tostring(root, encoding='unicode', method='xml')
                                print(f'Full xml = {xml_str}')
                                return papers
                            print(f"No data in returned XML, attempt {retry_count} of {max_retries}")
                            time.sleep(5)  # Wait 5 seconds before retrying
                            continue
                        
                        # If we get here, we have data, so break the retry loop
                        break
                except Exception as e:
                    retry_count += 1
                    if retry_count == max_retries:
                        print(f"Failed to retrieve data after {max_retries} attempts: {str(e)}")
                        return papers
                    print(f"Error on attempt {retry_count}: {str(e)}")
                    time.sleep(5)
                    continue

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
                    papers.append(self._process_paper_entry(entry))
                else:
                    # Stop processing since entries are sorted by last updated date
                    print(f'Current: {updated_date}. Up to: {one_day_ago}')
                    papers.append(self._process_paper_entry(entry))
                    return papers

            # Increment start index for the next batch
            start += max_results
            print(f'latest date: {updated_date}')
            time.sleep(5)
            if start>1200: # never retrieve more than 1600 results
                print('Found more than 1200 papers')
                break
        
        return papers
    
    def extract_titles(self, content):
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

    def filter_dicts_by_titles(self, dict_list, titles):
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

        

    def get_pdf_url(self, arxiv_url):
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