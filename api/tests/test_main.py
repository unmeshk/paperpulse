import pytest
from unittest.mock import patch, Mock, MagicMock
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import json
import os
import sys
import os
from pathlib import Path

# Add the parent directory to the Python path
sys.path.append(str(Path(__file__).parent.parent.parent))

from api.main import (
    process_data,
    retrieve_daily_results,
    identify_important_papers,
    get_pdf_url,
    combine_paper_info,
    extract_titles,
    filter_dicts_by_titles
)
from api.utils import add_markdown_links, download_pdf
from api.webs import create_blogpost
from api.agent import summarize_paper

# Fixtures
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

# Tests for process_data
def test_process_data(sample_entry):
    result = process_data(sample_entry)
    assert result['title'] == 'Test Paper Title'
    assert result['authors'] == ['Author One', 'Author Two']
    assert result['summary'] == 'This is a test summary'
    assert result['url'] == 'https://arxiv.org/abs/1234.5678'


# Tests for identify_important_papers
@patch('openai.chat.completions.create')
def test_identify_important_papers(mock_openai):
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
    
    summary = identify_important_papers(papers)
    assert summary == "Summary content\n\nTop 5 papers content"

# Tests for get_pdf_url
@patch('urllib.request.urlopen')
def test_get_pdf_url(mock_urlopen):
    mock_response = Mock()
    mock_response.read.return_value = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
        <entry>
            <link rel="related" title="pdf" href="https://arxiv.org/pdf/1234.5678" />
        </entry>
    </feed>
    """
    mock_urlopen.return_value.__enter__.return_value = mock_response

    url = get_pdf_url('https://arxiv.org/abs/1234.5678')
    assert url == 'https://arxiv.org/pdf/1234.5678'

# Tests for combine_paper_info
def test_combine_paper_info(sample_paper):
    result = combine_paper_info(sample_paper)
    expected = "**Title:** Test Paper Title\n**Authors:** Author One, Author Two\n**Summary:** This is a test summary\n"
    assert result == expected

# Tests for extract_titles
def test_extract_titles():
    content = """
    1. **Title One** - Description
    2. **Title Two** - Another description
    """
    titles = extract_titles(content)
    assert titles == ['Title One', 'Title Two']

# Tests for filter_dicts_by_titles
def test_filter_dicts_by_titles():
    dict_list = [
        {'title': 'Title One'},
        {'title': 'Title Two'},
        {'title': 'Title Three'}
    ]
    titles = ['Title One', 'Title Three']
    result = filter_dicts_by_titles(dict_list, titles)
    assert len(result) == 2
    assert result[0]['title'] == 'Title One'
    assert result[1]['title'] == 'Title Three'

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