from corpus.chunking import chunk_text

PARAGRAPH = (
    "Students may bring personal electronic devices to school. Devices must remain "
    "silenced and stored during instructional time unless a teacher directs otherwise."
)


def test_short_text_is_a_single_chunk():
    assert chunk_text(PARAGRAPH) == [PARAGRAPH]


def test_chunks_respect_max_size():
    text = "\n\n".join(f"Section {i}. {PARAGRAPH}" for i in range(30))
    chunks = chunk_text(text, max_chars=500)
    assert len(chunks) > 1
    assert all(len(c) <= 500 for c in chunks)


def test_no_content_is_lost():
    text = "\n\n".join(f"Unique marker {i} appears here. {PARAGRAPH}" for i in range(20))
    joined = " ".join(chunk_text(text, max_chars=500))
    for i in range(20):
        assert f"Unique marker {i}" in joined


def test_consecutive_chunks_overlap():
    """Overlap keeps a fact that straddles a boundary findable in one chunk."""
    text = "\n\n".join(f"Paragraph {i}. {PARAGRAPH}" for i in range(20))
    chunks = chunk_text(text, max_chars=500, overlap=120)
    for a, b in zip(chunks, chunks[1:]):
        tail = a[-40:]
        assert tail in b, "next chunk should begin with the previous chunk's tail"


def test_oversized_single_paragraph_is_split():
    text = " ".join(f"Sentence number {i} of an enormous unbroken paragraph." for i in range(60))
    chunks = chunk_text(text, max_chars=400)
    assert len(chunks) > 1
    assert all(len(c) <= 400 for c in chunks)


def test_whitespace_is_normalized():
    chunks = chunk_text("First   line\n\n\n\nSecond    line\r\nThird line")
    assert chunks == ["First line\n\nSecond line Third line"]


def test_form_feed_is_a_hard_chunk_boundary():
    """Extractors insert \\f to keep atomic units (table rows) from merging."""
    assert chunk_text("Alpha\fBeta\fGamma") == ["Alpha", "Beta", "Gamma"]


def test_form_feed_keeps_short_table_rows_separate():
    # Two short rows that would otherwise pack into one ~1200-char chunk.
    text = "Regular schedule: Period: First Period, Start: 7:50 AM\fRegular schedule: Period: Second Period, Start: 8:42 AM"
    chunks = chunk_text(text)
    assert len(chunks) == 2
    assert chunks[0].endswith("7:50 AM")
    assert chunks[1].endswith("8:42 AM")


def test_form_feed_edges_do_not_produce_empty_chunks():
    assert chunk_text("\fRow one\fRow two\f") == ["Row one", "Row two"]
