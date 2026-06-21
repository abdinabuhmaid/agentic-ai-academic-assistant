"""
ingestion.py
------------
The ingestion side of the pipeline. Takes a PDF file path and returns clean
text. This runs once per upload (not on every student request), which keeps
the per-request cost and latency low — one of the findings in the report.
"""

from pypdf import PdfReader


def extract_text_from_pdf(path):
    """
    Read a PDF and return its text as one string.
    Pages that can't be parsed (e.g. scanned images) simply contribute
    empty text rather than crashing the whole upload.
    """
    reader = PdfReader(path)
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    text = "\n".join(pages).strip()

    if not text:
        raise ValueError(
            "No text could be extracted from this PDF. It may be a scanned "
            "image — those need OCR, which this starter version does not do yet."
        )
    return text
