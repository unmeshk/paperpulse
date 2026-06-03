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
from api.settings import get_secret


# Fixtures
@pytest.fixture
def arxiv_client():
    return ArxivClient()

@pytest.fixture
def llm_agent():
    return Agent(gemini_api_key="dummy_key")

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
    <item>
        <title>Test Paper Title</title>
        <link>https://arxiv.org/abs/1234.5678</link>
        <description>arXiv:1234.5678v1 Announce Type: new Abstract: This is a test summary</description>
        <dc:creator xmlns:dc="http://purl.org/dc/elements/1.1/">Author One, Author Two</dc:creator>
    </item>
    """
    return ET.fromstring(xml_string)

@pytest.fixture
def mock_arxiv_response():
    return b"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/">
      <channel>
        <item>
          <title>Test Paper 1</title>
          <link>https://arxiv.org/abs/1234.5678</link>
          <description>arXiv:1234.5678v1 Announce Type: new Abstract: Summary 1</description>
          <dc:creator>Author One</dc:creator>
        </item>
        <item>
          <title>Test Paper 2</title>
          <link>https://arxiv.org/abs/8765.4321</link>
          <description>arXiv:8765.4321v1 Announce Type: new Abstract: Summary 2</description>
          <dc:creator>Author Two</dc:creator>
        </item>
      </channel>
    </rss>
    """

# ArxivClient Tests
class TestArxivClient:
    def test_process_paper_entry(self, arxiv_client, sample_entry):
        result = arxiv_client._process_paper_entry(sample_entry)
        assert result['title'] == 'Test Paper Title'
        assert result['authors'] == ['Author One', 'Author Two']
        assert result['summary'] == 'This is a test summary'
        assert result['url'] == 'https://arxiv.org/abs/1234.5678'

    @patch('urllib.request.urlopen')
    def test_retrieve_daily_results(self, mock_urlopen, mock_arxiv_response):
        mock_response = Mock()
        mock_response.read.return_value = mock_arxiv_response
        mock_urlopen.return_value.__enter__.return_value = mock_response

        client = ArxivClient(categories=['cs.LG'])
        with patch('time.sleep'):
            results = client.retrieve_daily_results()
        assert len(results) == 2
        assert results[0]['title'] == 'Test Paper 1'
        assert results[1]['title'] == 'Test Paper 2'

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
    def test_identify_important_papers(self, llm_agent):
        mock_response = Mock()
        mock_response.text = "Summary content"

        papers = [
            {
                'title': 'Test Paper',
                'authors': ['Author'],
                'summary': 'Summary',
                'url': 'https://arxiv.org/abs/1234.5678'
            }
        ]

        with patch.object(llm_agent.client.models, 'generate_content', return_value=mock_response):
            summary = llm_agent.identify_important_papers(papers)
        assert summary == "Summary content"

    def test_combine_paper_info(self, sample_paper, llm_agent):
        result = llm_agent._combine_paper_info(sample_paper)
        expected = "**Title:** Test Paper Title\n**URL:** https://arxiv.org/abs/1234.5678\n**Authors:** Author One, Author Two\n**Summary:** This is a test summary\n"
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
def test_create_blogpost(mock_open, monkeypatch):
    monkeypatch.setenv('PROJECT_DIR', '/tmp')
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


# get_secret tests
class TestGetSecret:
    @pytest.fixture
    def patch_secrets_dir(self, tmp_path, monkeypatch):
        """Redirect the /run/secrets lookup in api.settings to a tmp dir."""
        import api.settings as settings_mod
        original_path = settings_mod.Path
        secrets_dir = tmp_path / "secrets"
        secrets_dir.mkdir()

        def fake_path(arg):
            if arg == "/run/secrets":
                return secrets_dir
            return original_path(arg)

        monkeypatch.setattr(settings_mod, "Path", fake_path)
        return secrets_dir

    def test_reads_from_secrets_file_when_present(self, patch_secrets_dir):
        (patch_secrets_dir / "my_key").write_text("secret-from-file\n")
        assert get_secret("my_key") == "secret-from-file"

    def test_falls_back_to_env_when_file_absent(self, patch_secrets_dir, monkeypatch):
        monkeypatch.setenv("MY_KEY", "secret-from-env")
        assert get_secret("my_key") == "secret-from-env"

    def test_returns_none_when_neither_present(self, patch_secrets_dir, monkeypatch):
        monkeypatch.delenv("MISSING_KEY", raising=False)
        assert get_secret("missing_key") is None


if __name__ == '__main__':
    pytest.main(['-v'])