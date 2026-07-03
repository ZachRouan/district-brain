"""Text extraction for the supported corpus formats.

Google Docs exports arrive as .docx, .pdf, .txt, or .html — all covered here.
Extraction is deliberately plain: clean text out, everything else dropped.
"""

from pathlib import Path


class UnsupportedFormat(Exception):
    pass


SUPPORTED_EXTENSIONS = {".txt", ".md", ".html", ".htm", ".docx", ".pdf"}


def _decode(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def _extract_html(data: bytes) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(_decode(data), "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    # Emit one paragraph per block element so inline markup (<b>, <a>…) never
    # splits a sentence, and table rows flatten to one line each.
    blocks = []
    for el in soup.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote", "pre", "caption", "tr"]):
        if el.name == "tr":
            cells = [c.get_text(" ", strip=True) for c in el.find_all(["td", "th"])]
            text = " | ".join(c for c in cells if c)
        else:
            text = el.get_text(" ", strip=True)
        if text:
            blocks.append(text)
    return "\n\n".join(blocks) if blocks else soup.get_text(separator="\n")


def _extract_docx(fileobj) -> str:
    import docx

    document = docx.Document(fileobj)
    parts = [p.text for p in document.paragraphs]
    # Schedules commonly live in tables; flatten each row to one line.
    for table in document.tables:
        for row in table.rows:
            parts.append(" | ".join(cell.text.strip() for cell in row.cells))
    return "\n\n".join(part for part in parts if part.strip())


def _extract_pdf(fileobj) -> str:
    from pypdf import PdfReader

    reader = PdfReader(fileobj)
    return "\n\n".join(page.extract_text() or "" for page in reader.pages)


def extract_text(source, filename=None) -> str:
    """Extract clean text from a path or an open binary file object.

    `filename` supplies the extension when `source` is a file object.
    """
    if hasattr(source, "read"):
        name = filename or getattr(source, "name", "")
        extension = Path(name).suffix.lower()
        if extension in (".txt", ".md"):
            return _decode(source.read())
        if extension in (".html", ".htm"):
            return _extract_html(source.read())
        if extension == ".docx":
            return _extract_docx(source)
        if extension == ".pdf":
            return _extract_pdf(source)
        raise UnsupportedFormat(f"Unsupported file type: {extension or '(no extension)'}")

    path = Path(source)
    with open(path, "rb") as f:
        return extract_text(f, filename=path.name)
