### Contains all of the code to take the summaries and 
### create the blog post and place in the correct directory
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

def create_blogpost(summary, num_papers):
    """
    Creates a markdown file with specified naming convention and writes content.
    
    Args:
        content (str): The content to write to the markdown file
        date_obj (datetime): DateTime object used for file naming
    """
    todays_date = datetime.now().strftime('%Y-%m-%d')
    # Format the filename
    filename = f"{todays_date}-daily-summary.markdown"
    
    # Create the header with the current date
    header = f"""---
layout: post
title: ArXiV papers Summary ({num_papers} papers summarized)
date: {todays_date}
categories: summary
---
## Number of papers summarized: {num_papers}
"""

    # Combine header and content
    full_content = f"{header}\n\n{summary}"
    
    # Write to file
    with open(os.path.join(os.getenv('PROJECT_DIR'),'blog/_posts/',filename), 'w') as file:
        file.write(full_content)