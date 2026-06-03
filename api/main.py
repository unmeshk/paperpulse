import os
import pickle
import re
import logging

import urllib
import urllib.request as libreq

from datetime import datetime
import xml.etree.ElementTree as ET

from dotenv import load_dotenv
from api.utils import (
    extract_text_from_pdf,
    extract_images_from_pdf_base64,
    download_pdf,
)
from api.arxiv_client import ArxivClient
from api.agent import Agent
from api.file_handler import FileHandler
from api.settings import RSS_CATEGORIES

from api.webs import create_blogpost

logger = logging.getLogger(__name__)
logging.basicConfig(filename='myapp.log', level=logging.INFO)
logger.setLevel(logging.INFO)


def main():
    """
    Main function that orchestrates the retrieval and summarization process.
    """

    load_dotenv()
    dev_env=os.getenv("PROJECT_ENV")
    logger.info(dev_env)

    # initalize
    arxiv_client = ArxivClient(RSS_CATEGORIES)
    llm_agent = Agent(os.getenv("GEMINI_API_KEY"))
    file_handler = FileHandler(os.getenv("PROJECT_DIR"))
    papers = None

    try:       
        # if in dev mode, check to see if papers were downloaded earlier

        if dev_env=='dev':
            papers = file_handler.load_papers()
        
        if not papers:        
            logger.info('Retrieving daily results')
            papers = arxiv_client.retrieve_daily_results()
        
            if dev_env=='dev':
                file_handler.save_papers(papers)
                
        if not papers:
            logger.error('No papers retrieved')
            return
        
        logger.info(f'Retrieved: {len(papers)} papers')

        summary = llm_agent.identify_important_papers(papers)
    except Exception as e:
        print(f'Exception: {e}')
        return

    create_blogpost(summary, len(papers))

if __name__ == "__main__":
    main()

