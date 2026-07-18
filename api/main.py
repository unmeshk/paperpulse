import os
import pickle
import re
import sys
import logging

import urllib
import urllib.request as libreq

from datetime import datetime
import xml.etree.ElementTree as ET

from dotenv import load_dotenv
# TODO: remove these imports — they pull in pdfplumber/Pillow but the functions are not used by main().
# Kept commented as a marker until we decide whether to bring back PDF processing or delete utils.py outright.
# from api.utils import (
#     extract_text_from_pdf,
#     extract_images_from_pdf_base64,
#     download_pdf,
# )
from api.arxiv_client import ArxivClient
from api.agent import Agent
from api.file_handler import FileHandler
from api.settings import RSS_CATEGORIES, get_secret

from api.webs import create_blogpost

logger = logging.getLogger(__name__)
# LOG_DIR lets the container redirect log files to a host-mounted volume so runs
# survive `docker compose run --rm`. Defaults to CWD for local dev.
_log_dir = os.getenv("LOG_DIR", ".")
_log_path = os.path.join(_log_dir, "myapp.log")
logging.basicConfig(
    level=logging.INFO,
    handlers=[
        logging.FileHandler(_log_path),
        logging.StreamHandler(sys.stderr),
    ],
)
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
    llm_agent = Agent(get_secret("gemini_api_key"))
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
            # Empty feeds are a legitimate steady state (e.g. arXiv didn't publish
            # in the last cycle). Skip the blog post only — the per-category blurbs
            # below fetch their own feeds, and a user category can have papers on a
            # day the blog categories don't.
            logger.info('No papers retrieved; skipping today\'s post')
        else:
            logger.info(f'Retrieved: {len(papers)} papers')
            summary = llm_agent.identify_important_papers(papers)
            create_blogpost(summary, len(papers))
    except Exception as e:
        print(f'Exception: {e}')

    # Per-category blurbs for the personalized feed (Phase 1). Additive to the
    # public blog flow above; failures here must not break the blog post.
    try:
        from api.feeds import generate_category_blurbs, get_fetch_list, today_ny
        from api.settings import APP_DB_PATH, CONTENT_DIR

        if CONTENT_DIR:
            fetch_list = get_fetch_list(APP_DB_PATH)
            logger.info(f'Generating per-category blurbs for: {fetch_list}')
            papers_by_category = arxiv_client.retrieve_results_by_category(fetch_list)
            generate_category_blurbs(papers_by_category, llm_agent, CONTENT_DIR, today_ny())
        else:
            logger.info('CONTENT_DIR not set; skipping per-category blurbs')
    except Exception as e:
        logger.error(f'Per-category blurb generation failed: {e}')

if __name__ == "__main__":
    main()

