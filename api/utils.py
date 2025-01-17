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


def add_markdown_links(text, paper_list):
    """
    Replace occurrences of strings from text_list with markdown hyperlinks using corresponding urls
    
    Args:
        text (str): The source markdown text
        paper_list (list): List of dicts containing info about papers
    
    Returns:
        str: Modified text with markdown hyperlinks added
    """
    text_list = [p['title'] for p in paper_list]
    url_list = [p['url'] for p in paper_list]

    if len(text_list) != len(url_list):
        raise ValueError("text_list and url_list must have the same length")
        
    # Sort text_list and url_list by length of text (longest first)
    # This prevents shorter strings from matching inside longer ones
    pairs = sorted(zip(text_list, url_list), key=lambda x: len(x[0]), reverse=True)
    
    result = text
    for find_text, url in pairs:
        # Create markdown link format
        markdown_link = f'[{find_text}]({url})'
        # Replace all occurrences of the text with the markdown link
        result = result.replace(find_text, markdown_link)
        
    return result