import pytest
from unittest.mock import patch, Mock, MagicMock
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import sys
from pathlib import Path

# Add the parent directory to the Python path
sys.path.append(str(Path(__file__).parent.parent.parent))

from api.arxiv_client import ArxivClient
from api.agent import Agent
from api.file_handler import FileHandler
from api.utils import add_markdown_links, download_pdf
from api.webs import create_blogpost


# Fixtures
@pytest.fixture
def arxiv_client():
    return ArxivClient()

@pytest.fixture
def llm_agent():
    return Agent(openai_api_key="dummy_key")

@pytest.fixture
def file_handler():
    return FileHandler(base_dir="/tmp")

@pytest.fixture
def sample_paper():
    return {
        'title': 'Test Paper Title',
        'authors': ['Author One', 'Author Two'],
        'summary': 'This is a test summary',
        'url': 'https://arxiv.org/abs/1234.5678'
    }

@pytest.fixture
def sample_entry():
    xml_string = """
    <entry xmlns="http://www.w3.org/2005/Atom">
        <title>Test Paper Title</title>
        <author>
            <name>Author One</name>
        </author>
        <author>
            <name>Author Two</name>
        </author>
        <summary>This is a test summary</summary>
        <id>https://arxiv.org/abs/1234.5678</id>
        <updated>2025-01-17T12:00:00Z</updated>
    </entry>
    """
    return ET.fromstring(xml_string)

@pytest.fixture
def mock_arxiv_response():
    return """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
        <entry>
            <title>Test Paper 1</title>
            <author><name>Author One</name></author>
            <summary>Summary 1</summary>
            <id>https://arxiv.org/abs/1234.5678</id>
            <updated>2025-01-17T12:00:00Z</updated>
        </entry>
        <entry>
            <title>Test Paper 2</title>
            <author><name>Author Two</name></author>
            <summary>Summary 2</summary>
            <id>https://arxiv.org/abs/8765.4321</id>
            <updated>2025-01-17T11:00:00Z</updated>
        </entry>
    </feed>
    """

# ArxivClient Tests
class TestArxivClient:
    def test_process_paper_entry(self, arxiv_client, sample_entry):
        result = arxiv_client._process_paper_entry(sample_entry)
        assert result['title'] == 'Test Paper Title'
        assert result['authors'] == ['Author One', 'Author Two']
        assert result['summary'] == 'This is a test summary'
        assert result['url'] == 'https://arxiv.org/abs/1234.5678'

    #@patch('urllib.request.urlopen')
    #def test_retrieve_daily_results(self, mock_urlopen, arxiv_client, mock_arxiv_response):
    #    mock_response = Mock()
    #    mock_response.read.return_value = mock_arxiv_response.encode()
    #    mock_urlopen.return_value.__enter__.return_value = mock_response

    #    results = arxiv_client.retrieve_daily_results()
    #    assert len(results) == 2
    #    assert results[0]['title'] == 'Test Paper 1'
    #    assert results[1]['title'] == 'Test Paper 2'

    @patch('urllib.request.urlopen')
    def test_get_pdf_url(self, mock_urlopen, arxiv_client):
        mock_response = Mock()
        mock_response.read.return_value = """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
            <entry>
                <link rel="related" title="pdf" href="https://arxiv.org/pdf/1234.5678" />
            </entry>
        </feed>
        """.encode()
        mock_urlopen.return_value.__enter__.return_value = mock_response

        url = arxiv_client.get_pdf_url('https://arxiv.org/abs/1234.5678')
        assert url == 'https://arxiv.org/pdf/1234.5678'

    def test_extract_titles(self, arxiv_client):
        content = """
        1. **Title One** - Description
        2. **Title Two** - Another description
        """
        titles = arxiv_client.extract_titles(content)
        assert titles == ['Title One', 'Title Two']

    # Tests for filter_dicts_by_titles
    def test_filter_dicts_by_titles(self, arxiv_client):
        dict_list = [
            {'title': 'Title One'},
            {'title': 'Title Two'},
            {'title': 'Title Three'}
        ]
        titles = ['Title One', 'Title Three']
        result = arxiv_client.filter_dicts_by_titles(dict_list, titles)
        assert len(result) == 2
        assert result[0]['title'] == 'Title One'
        assert result[1]['title'] == 'Title Three'



# Agent Tests
class TestAgent:
    @patch('openai.chat.completions.create')
    def test_identify_important_papers(self, mock_openai, llm_agent):
        mock_response = Mock()
        mock_response.choices = [
            Mock(message=Mock(content="Summary content\n\nTop 5 papers content"))
        ]
        mock_openai.return_value = mock_response

        papers = [
            {
                'title': 'Test Paper',
                'authors': ['Author'],
                'summary': 'Summary',
                'url': 'https://arxiv.org/abs/1234.5678'
            }
        ]
        
        summary = llm_agent.identify_important_papers(papers)
        assert summary == "Summary content\n\nTop 5 papers content"

    def test_combine_paper_info(self, sample_paper, llm_agent):
        result = llm_agent._combine_paper_info(sample_paper)
        expected = "**Title:** Test Paper Title\n**Authors:** Author One, Author Two\n**Summary:** This is a test summary\n"
        assert result == expected

# FileHandler Tests
class TestFileHandler:
    def test_save_and_load_papers(self, file_handler, sample_paper):
        test_date = datetime(2025, 1, 1)
        file_handler.save_papers([sample_paper], date=test_date)
        
        loaded_papers = file_handler.load_papers(date=test_date)
        assert len(loaded_papers) == 1
        assert loaded_papers[0]['title'] == sample_paper['title']

# utils tests
# Tests for add_markdown_links
def test_add_markdown_links():
    text = "Check out Paper One and Paper Two"
    paper_list = [
        {'title': 'Paper One', 'url': 'http://example.com/1'},
        {'title': 'Paper Two', 'url': 'http://example.com/2'}
    ]
    result = add_markdown_links(text, paper_list)
    expected = 'Check out <a href="http://example.com/1" target="_blank">Paper One</a> and <a href="http://example.com/2" target="_blank">Paper Two</a>'
    assert result == expected

# Tests for download_pdf
@patch('urllib.request.urlopen')
def test_download_pdf(mock_urlopen):
    mock_response = Mock()
    mock_response.read.return_value = b"PDF content"
    mock_urlopen.return_value.__enter__.return_value = mock_response

    with patch('builtins.open', create=True) as mock_open:
        result = download_pdf('http://example.com/paper.pdf', 'test.pdf')
        assert result == '/tmp/test.pdf'
        mock_open.assert_called_once_with('/tmp/test.pdf', 'wb')

# Tests for create_blogpost
@patch('builtins.open', create=True)
def test_create_blogpost(mock_open):
    summary = "Test summary content"
    num_papers = 5
    
    create_blogpost(summary, num_papers)
    
    mock_open.assert_called_once()
    args = mock_open.call_args[0]
    assert args[1] == 'w'
    handle = mock_open.return_value.__enter__.return_value
    written_content = handle.write.call_args[0][0]
    
    # Check front matter contains num_papers
    assert "categories: summary" in written_content
    assert "num_papers: 5" in written_content
    
    # Check content
    assert "Test summary content" in written_content
    
    # Check YAML front matter format
    assert written_content.startswith("---\n")
    assert "---\n" in written_content[3:]  # Check for closing front matter delimiter


if __name__ == '__main__':
    pytest.main(['-v'])