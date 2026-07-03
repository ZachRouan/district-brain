"""Text extraction for the supported corpus formats.

Google Docs exports arrive as .docx, .pdf, .txt, or .html — all covered here.
Extraction is deliberately plain: clean text out, everything else dropped.

Tabular data gets special handling. A raw table row flattens to a pipe-delimited
fragment ("Period 1 | 7:50 AM | 8:38 AM") with almost no semantic overlap against
a natural-language question, so it embeds poorly and retrieval misses it. Each
table row is instead *enriched* into a sentence-shaped chunk carrying its
inherited context — the nearest preceding heading and the column headers — e.g.
"Regular schedule: Period: Period 1, Start: 7:50 AM, End: 8:38 AM". This text is
what gets embedded AND what appears in citations, so staff see exactly what the
model saw. Enriched rows are separated with a form feed (see chunking.FORM_FEED)
so each becomes its own chunk rather than being merged into a diluted table blob.

Context is the nearest heading; the document title is used only as a *fallback*
when a table sits above every heading. Prepending the always-present title
measurably hurts recall — it is semantically distant from a "what time…" question
and pushes even the correct row past the retrieval cutoff (dev bell-schedule row:
0.61 with the title vs 0.46 without; the hash embedder likewise 0.63 vs 0.58,
straddling the 0.60 cutoff) — and the title is already shown on every citation,
so nothing is lost by keeping it out of the embedded text.
"""

import re
from pathlib import Path

from .chunking import FORM_FEED


class UnsupportedFormat(Exception):
    pass


SUPPORTED_EXTENSIONS = {".txt", ".md", ".html", ".htm", ".docx", ".pdf"}


def _decode(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


# --- Table-row enrichment (shared across markdown / docx / html) -------------


def _with_context(context, body):
    context = (context or "").strip()
    return f"{context}: {body}" if context else body


def _labeled_row(context, headers, cells):
    """A row rendered as "Header: value, Header: value", prefixed with context."""
    fields = []
    for idx, cell in enumerate(cells):
        cell = cell.strip()
        if not cell:
            continue
        header = headers[idx].strip() if headers and idx < len(headers) else ""
        fields.append(f"{header}: {cell}" if header else cell)
    return _with_context(context, ", ".join(fields)) if fields else ""


def _pipe_row(context, cells):
    """Fallback for a headerless table: the pipe format, still context-prefixed."""
    body = " | ".join(cell.strip() for cell in cells if cell.strip())
    return _with_context(context, body) if body else ""


def _render_table(context, header_cells, data_rows):
    """Render a table's data rows as enriched chunks, each its own form-feed unit.

    `context` is the nearest heading (or the document title as a fallback).
    header_cells is None for a headerless table (pipe fallback). Returns "" when
    the table has no usable content.
    """
    rendered = []
    for cells in data_rows:
        line = _labeled_row(context, header_cells, cells) if header_cells else _pipe_row(context, cells)
        if line:
            rendered.append(line)
    if not rendered:
        return ""
    # Wrap in form feeds so each row is isolated from its neighbours and from
    # surrounding prose when chunked.
    return FORM_FEED + FORM_FEED.join(rendered) + FORM_FEED


# --- Markdown ----------------------------------------------------------------

_MD_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")


def _split_md_row(line: str):
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def _is_md_separator(line: str) -> bool:
    """A GitHub-flavored-markdown table separator, e.g. `| --- | :--: |`."""
    if "|" not in line and "-" not in line:
        return False
    cells = _split_md_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{1,}:?", cell.strip() or "") for cell in cells)


def _extract_markdown(data: bytes, title=None) -> str:
    """Markdown passes through unchanged except GFM tables, whose rows are
    enriched with the document title and nearest heading. Non-table content is
    byte-for-byte what plain decoding produced."""
    text = _decode(data).replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    out = []
    nearest_heading = None
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        heading = _MD_HEADING.match(line)
        if heading:
            nearest_heading = heading.group(2).strip()
            out.append(line)
            i += 1
            continue
        # A table starts where a header line is followed by a separator line.
        if (
            "|" in line
            and not _is_md_separator(line)
            and i + 1 < n
            and _is_md_separator(lines[i + 1])
        ):
            header_cells = _split_md_row(line)
            i += 2
            data_rows = []
            while i < n and lines[i].strip() and "|" in lines[i]:
                data_rows.append(_split_md_row(lines[i]))
                i += 1
            rendered = _render_table(nearest_heading or title, header_cells, data_rows)
            if rendered:
                out.append(rendered)
            continue
        out.append(line)
        i += 1
    return "\n".join(out)


# --- HTML --------------------------------------------------------------------

_HTML_HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_HTML_TEXT_BLOCKS = {"p", "li", "blockquote", "pre", "caption"}


def _render_html_table(table, title, nearest_heading):
    rows = table.find_all("tr")
    if not rows:
        return ""
    caption = table.find("caption")
    heading = caption.get_text(" ", strip=True) if caption else nearest_heading

    header_cells = None
    data_rows = []
    for tr in rows:
        header_tags = tr.find_all("th")
        if header_tags and header_cells is None:
            header_cells = [c.get_text(" ", strip=True) for c in header_tags]
            continue
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        if any(cells):
            data_rows.append(cells)
    return _render_table(heading or title, header_cells, data_rows)


def _extract_html(data: bytes, title=None) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(_decode(data), "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()

    blocks = []
    nearest_heading = None

    def walk(node):
        nonlocal nearest_heading
        for el in node.children:
            name = getattr(el, "name", None)
            if name is None:
                continue
            if name == "table":
                rendered = _render_html_table(el, title, nearest_heading)
                if rendered:
                    blocks.append(rendered)
            elif name in _HTML_HEADINGS:
                text = el.get_text(" ", strip=True)
                if text:
                    nearest_heading = text
                    blocks.append(text)
            elif name in _HTML_TEXT_BLOCKS:
                text = el.get_text(" ", strip=True)
                if text:
                    blocks.append(text)
            else:
                walk(el)  # descend into containers (body, div, section, …)

    walk(soup.body or soup)
    return "\n\n".join(blocks) if blocks else soup.get_text(separator="\n")


# --- docx --------------------------------------------------------------------


def _iter_docx_blocks(document):
    """Yield the document's paragraphs and tables in body order (python-docx
    exposes them as separate lists, losing the interleaving we need for heading
    context)."""
    from docx.oxml.table import CT_Tbl
    from docx.oxml.text.paragraph import CT_P
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    for child in document.element.body.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, document)
        elif isinstance(child, CT_Tbl):
            yield Table(child, document)


def _render_docx_table(table, title, nearest_heading):
    rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
    if not rows:
        return ""
    # Treat the first row as the header when it is fully populated and there is
    # at least one data row; otherwise fall back to the pipe format.
    has_header = len(rows) >= 2 and all(cell for cell in rows[0])
    header_cells = rows[0] if has_header else None
    data_rows = rows[1:] if has_header else rows
    return _render_table(nearest_heading or title, header_cells, data_rows)


def _extract_docx(fileobj, title=None) -> str:
    import docx
    from docx.table import Table

    document = docx.Document(fileobj)
    blocks = []
    nearest_heading = None
    for block in _iter_docx_blocks(document):
        if isinstance(block, Table):
            rendered = _render_docx_table(block, title, nearest_heading)
            if rendered:
                blocks.append(rendered)
            continue
        text = block.text.strip()
        if not text:
            continue
        style = (block.style.name if block.style else "") or ""
        if style.startswith(("Heading", "Title")):
            nearest_heading = text
        blocks.append(text)
    return "\n\n".join(blocks)


# --- dispatch ----------------------------------------------------------------


def _extract_pdf(fileobj) -> str:
    from pypdf import PdfReader

    reader = PdfReader(fileobj)
    return "\n\n".join(page.extract_text() or "" for page in reader.pages)


def extract_text(source, filename=None, title=None) -> str:
    """Extract clean text from a path or an open binary file object.

    `filename` supplies the extension when `source` is a file object. `title` is
    the document's title, woven into enriched table-row chunks so a schedule row
    still matches a natural-language question (see module docstring).
    """
    if hasattr(source, "read"):
        name = filename or getattr(source, "name", "")
        extension = Path(name).suffix.lower()
        if extension == ".txt":
            return _decode(source.read())
        if extension == ".md":
            return _extract_markdown(source.read(), title=title)
        if extension in (".html", ".htm"):
            return _extract_html(source.read(), title=title)
        if extension == ".docx":
            return _extract_docx(source, title=title)
        if extension == ".pdf":
            return _extract_pdf(source)
        raise UnsupportedFormat(f"Unsupported file type: {extension or '(no extension)'}")

    path = Path(source)
    with open(path, "rb") as f:
        return extract_text(f, filename=path.name, title=title)
