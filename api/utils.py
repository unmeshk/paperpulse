import pdfplumber
import io
import base64
import fitz  # PyMuPDF
import urllib
import os
from PIL import Image
import urllib.request as libreq

def extract_text_from_pdf(pdf_content):
    """
    Extracts text from the PDF content.

    Args:
        pdf_content (str): The path or binary content of the PDF.

    Returns:
        str: Extracted text.
    """
    text = ""

    pdf_stream = io.BytesIO(pdf_content)
    with pdfplumber.open(pdf_stream) as pdf:
        for page in pdf.pages:
            text += page.extract_text() + "\n"
    return text.strip()

def extract_images_from_pdf_base64(pdf_content):
    """
    Extracts images from the PDF binary content and returns them as base64-encoded strings.

    Args:
        pdf_content (bytes): Binary content of the PDF.

    Returns:
        list: A list of base64-encoded image strings.
    """
    images_base64 = []

    # Wrap the binary content in a BytesIO object
    pdf_stream = io.BytesIO(pdf_content)

    # Open the PDF
    pdf_document = fitz.open(stream=pdf_stream, filetype="pdf")

    # Extract images from each page
    for page in pdf_document:
        for img in page.get_images(full=True):
            xref = img[0]
            base_image = pdf_document.extract_image(xref)
            image_bytes = base_image["image"]
            image = Image.open(io.BytesIO(image_bytes))

            # Convert the image to a base64 string
            buffered = io.BytesIO()
            image.save(buffered, format=image.format)
            img_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")

            images_base64.append(img_base64)

    return images_base64

def download_pdf(pdf_url, filename):
    """
    Downloads a PDF from a given URL and saves it to /tmp/filename

    Args:
        pdf_url (str): The URL of the PDF to download.
        filename (str): The filename to save the PDF as.
    """
    filepath  = os.path.join('/tmp/',filename)
    try:
        with urllib.request.urlopen(pdf_url) as response, open(filepath, 'wb') as outfile:
            outfile.write(response.read())
        print(f"Successfully downloaded PDF to {filename}")
        return filepath

    except urllib.error.URLError as e:
        print(f"Error: Could not download PDF from URL. {e}")
        return None
    except Exception as e:
          print(f"An unexpected error occurred during PDF download: {e}")
          return None

def normalize_text(text):
    """
    Normalize text by removing punctuation, extra spaces, and converting to lowercase
    """
    import re
    # Convert to lowercase and replace newlines with spaces
    text = text.lower().replace('\n', ' ')
    # Remove punctuation except hyphens between words
    text = re.sub(r'[^\w\s-]', ' ', text)
    # Replace multiple spaces with single space
    text = re.sub(r'\s+', ' ', text)
    # Remove spaces around hyphens
    text = re.sub(r'\s*-\s*', '-', text)
    return text.strip()

def find_title_in_text(normalized_text, normalized_title):
    """
    Find if a normalized title exists in normalized text
    Args:
        normalized_text (str): The normalized text to search in
        normalized_title (str): The normalized title to search for
    Returns:
        bool: True if the title is found, False otherwise
    """
    import re
    # Create a pattern that allows for flexible whitespace between words
    words = normalized_title.split()
    pattern = r'\b' + r'\s+'.join(re.escape(word) for word in words) + r'\b'
    match = re.search(pattern, normalized_text)
    return match is not None

def get_last_names(authors_list):
    """
    Extract last names from list of author names
    """
    last_names = []
    for author in authors_list:
        # Split on spaces and take the last part as the last name
        parts = author.strip().split()
        if parts:
            last_names.append(parts[-1])
    return last_names

def find_author_citations(text):
    """
    Find author citations in text in format "Author et al. (YEAR)"
    or "Author and Author (YEAR)" or "Author (YEAR)"
    """
    import re
    # Pattern matches:
    # 1. Single author: "Smith (2023)"
    # 2. Two authors: "Smith and Jones (2023)"
    # 3. Multiple authors: "Smith et al. (2023)"
    patterns = [
        r'([A-Z][a-z]+)\s+et\s+al\.\s*\((\d{4})\)',  # Smith et al. (2023)
        r'([A-Z][a-z]+)\s+and\s+([A-Z][a-z]+)\s*\((\d{4})\)',  # Smith and Jones (2023)
        r'([A-Z][a-z]+)\s*\((\d{4})\)'  # Smith (2023)
    ]
    
    citations = []
    for pattern in patterns:
        matches = re.finditer(pattern, text)
        for match in matches:
            if 'et al.' in match.group():
                citations.append((match.group(1), match.group(2), match.group()))  # (author, year, full_citation)
            elif 'and' in match.group():
                citations.append((f"{match.group(1)} and {match.group(2)}", match.group(3), match.group()))
            else:
                citations.append((match.group(1), match.group(2), match.group()))
    return citations

def extract_year_from_url(url):
    """
    Extract year from arXiv URL or return None if not found
    Args:
        url (str): The arXiv URL to extract year from
    Returns:
        str: Year in YYYY format, or None if not found
    """
    import re
    # ArXiv URLs typically contain year in format YYMM
    match = re.search(r'/(\d{2})(\d{2})\.\d+', url)
    if match:
        year = '20' + match.group(1)  # Convert YY to 20YY
        return year
    return None

def add_markdown_links(text, paper_list):
    """
    Replace occurrences of paper titles and author citations with markdown hyperlinks
    
    Args:
        text (str): The source markdown text
        paper_list (list): List of dicts containing paper info with keys: 'title', 'authors', 'url'
    
    Returns:
        str: Modified text with markdown hyperlinks added
    """
    result = text
    
    # First handle title matches with normalization
    # Create normalized version of the input text
    normalized_result = normalize_text(result)
    
    # Create title pairs with normalized versions
    title_pairs = []
    for paper in paper_list:
        original_title = paper['title']
        normalized_title = normalize_text(original_title)
        title_pairs.append((original_title, normalized_title, paper['url']))
    
    # Sort by normalized title length
    title_pairs.sort(key=lambda x: len(x[1]), reverse=True)
    
    for original_title, normalized_title, url in title_pairs:
        # Check if normalized title exists in normalized text
        if find_title_in_text(normalized_result, normalized_title):
            # Create markdown link with original title
            markdown_link = f'<a href="{url}" target="_blank">{original_title}</a>'
            # Find and replace the original text that matched
            # We use word boundaries to ensure we match complete words
            import re
            pattern = re.compile(re.escape(original_title).replace(r'\ ', r'\s+'), re.IGNORECASE)
            result = pattern.sub(lambda m: markdown_link, result)
    
    # Then handle author citations
    citations = find_author_citations(result)
    
    for author, year, full_citation in citations:
        matching_papers = []
        
        # For each paper, check if it matches the author and year
        for paper in paper_list:
            paper_year = extract_year_from_url(paper['url'])
            if not paper_year:
                continue
                
            last_names = get_last_names(paper['authors'])
            
            # For "Author1 and Author2 (YEAR)" citations
            if ' and ' in author:
                author1, author2 = author.split(' and ')
                if (author1 in last_names and author2 in last_names and 
                    year == paper_year):
                    matching_papers.append(paper)
            # For single author or "et al." citations
            elif author in last_names and year == paper_year:
                matching_papers.append(paper)
        
        # Only add link if there's exactly one matching paper
        if len(matching_papers) == 1:
            paper = matching_papers[0]
            markdown_link = f'<a href="{paper["url"]}" target="_blank">{full_citation}</a>'
            result = result.replace(full_citation, markdown_link)
    
    return result