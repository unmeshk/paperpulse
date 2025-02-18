import pickle
from datetime import datetime
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class FileHandler:
    def __init__(self, base_dir):
        self.base_dir = base_dir

    def save_papers(self, papers, date=None):
        """Save papers to pickle file"""
        date = date or datetime.today()
        filename = f'papers-{date.strftime("%Y-%m-%d")}.pkl'
        with open(os.path.join(self.base_dir, filename), 'wb') as f:
            pickle.dump(papers, f)

    def load_papers(self, date=None):
        """Load papers from pickle file"""
        date = date or datetime.today()
        filename = f'papers-{date.strftime("%Y-%m-%d")}.pkl'
        filepath = os.path.join(self.base_dir, filename)
        if os.path.exists(filepath):
            with open(filepath, 'rb') as f:
                return pickle.load(f)
        return None