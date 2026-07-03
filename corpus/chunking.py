"""Paragraph-aware chunking.

Documents split into retrieval-sized chunks along paragraph boundaries where
possible, with a short overlap seeded from the previous chunk so a fact that
straddles a boundary is still findable inside a single chunk.
"""

import re


def _normalize_paragraphs(text):
    """Paragraphs with all inner whitespace collapsed; empty ones dropped."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = re.split(r"\n\s*\n", text)
    return [p for p in (re.sub(r"\s+", " ", p).strip() for p in paragraphs) if p]


def _split_oversized(paragraph, max_chars):
    """Split a paragraph longer than max_chars at sentence boundaries,
    hard-wrapping any single sentence that is itself too long."""
    parts, current = [], ""
    for sentence in re.split(r"(?<=[.!?])\s+", paragraph):
        while len(sentence) > max_chars:
            cut = sentence.rfind(" ", 0, max_chars)
            cut = cut if cut > 0 else max_chars
            parts.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        if not current:
            current = sentence
        elif len(current) + 1 + len(sentence) <= max_chars:
            current += " " + sentence
        else:
            parts.append(current)
            current = sentence
    if current:
        parts.append(current)
    return parts


def _overlap_tail(chunk, overlap, budget):
    """The tail of `chunk` to seed the next chunk with: at most `overlap`
    characters, snapped to a word start, and never more than `budget`."""
    if overlap <= 0 or budget <= 0:
        return ""
    tail = chunk[-min(overlap, budget) :]
    space = tail.find(" ")
    return tail[space + 1 :] if space != -1 else tail


def chunk_text(text, max_chars=1200, overlap=150):
    """Split `text` into chunks of at most `max_chars` characters."""
    pieces = []
    for paragraph in _normalize_paragraphs(text):
        if len(paragraph) <= max_chars:
            pieces.append(paragraph)
        else:
            pieces.extend(_split_oversized(paragraph, max_chars))

    chunks, current = [], ""
    for piece in pieces:
        if not current:
            current = piece
        elif len(current) + 2 + len(piece) <= max_chars:
            current += "\n\n" + piece
        else:
            chunks.append(current)
            seed = _overlap_tail(current, overlap, budget=max_chars - len(piece) - 1)
            current = f"{seed} {piece}" if seed else piece
    if current:
        chunks.append(current)
    return chunks
