# pdf_loader.py
import io
from PyPDF2 import PdfReader

def load_pdf(file_bytes: bytes):
    """
    Load a PDF file from raw bytes and return text.
    """
    try:
        pdf_stream = io.BytesIO(file_bytes)
        reader = PdfReader(pdf_stream)
        text = ""

        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"

        return text.strip()

    except Exception as e:
        return f"❌ Error reading PDF: {e}"
