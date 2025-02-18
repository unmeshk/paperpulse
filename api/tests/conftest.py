import os
import sys
from pathlib import Path

# Get the absolute path of the api directory
api_dir = str(Path(__file__).parent.parent)

# Add the api directory to Python path
if api_dir not in sys.path:
    sys.path.insert(0, api_dir)

# This helps pytest find the api package
pytest_plugins = []