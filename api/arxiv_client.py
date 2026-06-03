import time
import logging
import re
import urllib.request as libreq

import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

from api.settings import RSS_CATEGORIES

logger = logging.getLogger(__name__)

_RSS_NS = {
    'dc': 'http://purl.org/dc/elements/1.1/',
    'arxiv': 'http://arxiv.org/schemas/atom',
}

class ArxivClient:
    def __init__(self, categories=RSS_CATEGORIES):
        self.categories = categories
        self.base_url = 'https://rss.arxiv.org/rss'

    def _process_paper_entry(self, item):
        title = (item.findtext('title') or '').strip()
        url = (item.findtext('link') or '').strip()

        # description format: "arXiv:XXXX.XXXXvN Announce Type: TYPE Abstract: [text]"
        description = item.findtext('description') or ''
        abstract_match = re.search(r'Abstract:\s*(.*)', description, re.DOTALL)
        summary = abstract_match.group(1).strip() if abstract_match else description.strip()

        # dc:creator contains all authors comma-separated
        creator = item.findtext('dc:creator', namespaces=_RSS_NS) or ''
        authors = [a.strip() for a in creator.split(',') if a.strip()]

        return {
            'title': title,
            'authors': authors,
            'summary': summary,
            'url': url,
        }

    def retrieve_daily_results(self):
        papers = []
        seen_urls = set()
        max_retries = 5

        for i, category in enumerate(self.categories):
            if i > 0:
                time.sleep(3)

            url = f'{self.base_url}/{category}'
            root = None

            for attempt in range(1, max_retries + 1):
                try:
                    with libreq.urlopen(url, timeout=30) as response:
                        root = ET.fromstring(response.read())
                    break
                except Exception as e:
                    if attempt == max_retries:
                        print(f"Failed to fetch {category} after {max_retries} attempts: {e}")
                    else:
                        print(f"Attempt {attempt} error for {category}: {e}")
                        time.sleep(5)

            if root is None:
                continue

            items = root.findall('.//item')

            # Find the most recent pubDate in this feed and keep only items from that date.
            # Guards against mixed-date feeds and partial intra-day data.
            pub_dates = []
            for item in items:
                raw = item.findtext('pubDate')
                if raw:
                    try:
                        pub_dates.append(parsedate_to_datetime(raw).date())
                    except Exception:
                        pass

            latest_date = max(pub_dates) if pub_dates else None

            for item in items:
                if latest_date:
                    raw = item.findtext('pubDate')
                    try:
                        item_date = parsedate_to_datetime(raw).date()
                        if item_date != latest_date:
                            continue
                    except Exception:
                        pass

                paper = self._process_paper_entry(item)
                if paper and paper['url'] not in seen_urls:
                    seen_urls.add(paper['url'])
                    papers.append(paper)

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
            return re.sub(r'\s+', ' ', text.strip()).replace('\n', '')

        normalized_titles = [normalize(title) for title in titles]
        return [item for item in dict_list if normalize(item.get('title', '')) in normalized_titles]

    def get_pdf_url(self, arxiv_url):
        """
        Extracts the PDF URL from an arXiv abstract page URL using the arXiv API.

        Args:
            arxiv_url (str): The URL of the arXiv abstract page.

        Returns:
            str: The URL of the PDF, or None if not found.
        """
        match = re.search(r'abs/([\w\.\/]+)', arxiv_url)
        if not match:
            return None
        arxiv_id = match.group(1)

        api_url = f'http://export.arxiv.org/api/query?id_list={arxiv_id}'

        try:
            with libreq.urlopen(api_url) as response:
                xml_content = response.read()

            tree = ET.fromstring(xml_content)

            namespaces = {
                'atom': 'http://www.w3.org/2005/Atom',
                'arxiv': 'http://arxiv.org/schemas/atom'
            }

            for entry in tree.findall('atom:entry', namespaces):
                for link in entry.findall('atom:link', namespaces):
                    if link.get('rel') == 'related' and link.get('title') == 'pdf':
                        return link.get('href')
            return None

        except Exception as e:
            logger.error(f"An unexpected error occurred {e}")
            return None
