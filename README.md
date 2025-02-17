# Paperpulse - A Daily ArXiv ML/AI Paper Summarizer
This project automatically retrieves, analyzes, and summarizes the latest Machine Learning, Artificial Intelligence, Computer Vision, and Computational Linguistics papers from ArXiv. It creates daily blog posts with thematic summaries of new research, making it easier to stay up-to-date with the latest developments in these fields.

## Features
- Daily retrieval of new papers from ArXiv in ML, AI, CV, and CL categories
- Automatic thematic grouping and summarization of papers using OpenAI API
- Generation of blog posts with summaries and hyperlinked references using Jekyll

## TODO
- Identification of top papers based on a simple recommendation engine
- Detailed analysis of top papers including methodology and results

## Main Requirements
Python 3.x
Jekyll 
OpenAI API key

## Installation
Clone the repository: `git clone [repository-url]`
cd paperpulse

## Install the required packages:
create a virtual env and then `pip install -r requirements.txt`

## Set up environment variables:
Create a .env file in the root directory with the following variables:
```
OPENAI_API_KEY=[your-openai-api-key]
PROJECT_ENV=dev  # or 'prod' for production. 
PROJECT_DIR=[path-to-project-directory]
```

In dev mode, the downloaded paper info is stored to a file with today's date. If run again, info from the file is used instead of pinging the ArXiv API again. 

## Usage

### To generate daily summaries: 
`python main.py`

This will:
- Retrieve the latest paper info (title, authors, abstract) from ArXiv
- Process and analyze this info to generate thematic summaries
- Create a blog post in the blog/_posts directory

### To start the jekyll server: 
`docker compose up --build`

This will:
- start a server at localhost:4000 that shows the blog.

### Tests
`pytest api/tests/test_main.py`

## Development vs Production

### Development mode (PROJECT_ENV=dev):
- Saves retrieved papers to pickle files for faster development
- Enables additional debugging output

### Production mode (PROJECT_ENV=prod):
- Always retrieves papers directly from ArXiv
- Minimizes debug output
- Optimized for production deployment

## Project Structure
- main.py: Core script for paper retrieval and processing
- arxiv_client.py: Handles the arxiv api call
- agent.py: OpenAI API integration for paper analysis
- file_handler.py: Save and load paper info from disk
- utils.py: Utility functions for PDF processing and text manipulation
- webs.py: Blog post generation functionality
- settings.py: Configuration and prompt templates
- tests/test_main.py: Unit tests for core functionality

## Contributing
- Fork the repository
- Create a feature branch (git checkout -b feature/AmazingFeature)
- Commit your changes (git commit -m 'Add some AmazingFeature')
- Push to the branch (git push origin feature/AmazingFeature)
- Open a Pull Request

## License
MIT License 

## Acknowledgments
- ArXiv for providing the research paper API
