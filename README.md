# Paperpulse - A Daily ArXiv ML/AI Paper Summarizer
This project automatically retrieves, analyzes, and summarizes the latest Machine Learning (**cs.LG**), Artificial Intelligence (**cs.AI**), Computer Vision (**cs.CV**), and Computation and Language (**cs.CL**) papers from ArXiv. It creates daily blog posts with thematic summaries of new research, making it easier to stay up-to-date with the latest developments in these fields.

You can see the resulting site online at: <https://paperpulse.ukurup.com>

## Features
- Daily retrieval of new papers from ArXiv in ML, AI, CV, and CL categories
- Automatic thematic grouping and summarization of papers using OpenAI API
- Generation of blog posts with summaries and hyperlinked references using Jekyll

### TODO
- Identification of top papers based on a simple recommendation engine
- Detailed analysis of top papers including methodology and results

## Main Requirements
- Python 3.x
- Jekyll 
- OpenAI API key

## Installation
- Clone the repository: `git clone [repository-url]`
- cd paperpulse
- create a virtual env and then `pip install -r requirements.txt`

## Set up environment variables:
Create a .env file in the root directory with the following variables:
```
OPENAI_API_KEY=[your-openai-api-key]
PROJECT_ENV=dev  # or 'prod' for production. 
PROJECT_DIR=[path-to-project-directory]
```

In `dev` mode, when `main.py` is run, the paper info retrieved via the ArXiv API is stored to the file `papers-<today's date>.pkl` in `PROJECT_DIR`. If `main.py` run again, info from this file is used instead of pinging the ArXiv API once more.

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

If you want to deploy this blog in a more prod environment, you can set `PROJECT_ENV=prod` and use `docker-compose -f docker-compose.prod.yml up -d` but you will have to set up *nginx* and *SSL* first. You'll also have to create a cron job that runs `python main.py` once a day.

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
`/api`
- `main.py`: Core script for paper retrieval and processing
- `arxiv_client.py`: Handles the arxiv api call
- `agent.py`: OpenAI API integration for paper analysis
- `file_handler.py`: Save and load paper info from disk
- `utils.py`: Utility functions for PDF processing and text manipulation
- `webs.py`: Blog post generation functionality
- `settings.py`: Configuration and prompt templates
- `tests/test_main.py`: Unit tests of core functionality
`/blog`: All blog (jekyll) related functionality including the daily posts that are created by `main.py`

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
