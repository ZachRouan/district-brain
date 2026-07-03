import pytest

from corpus.extractors import UnsupportedFormat, extract_text


def minimal_pdf(text: str) -> bytes:
    """Assemble a tiny but valid one-page PDF containing `text`."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref_pos = len(out)
    out += b"xref\n0 %d\n" % (len(objects) + 1) + b"0000000000 65535 f \n"
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (len(objects) + 1, xref_pos)
    return bytes(out)


def test_txt_and_md(tmp_path):
    for name in ("policy.txt", "policy.md"):
        path = tmp_path / name
        path.write_text("Devices must remain silenced during class.")
        assert "silenced during class" in extract_text(path)


def test_html_strips_markup_and_scripts(tmp_path):
    path = tmp_path / "handbook.html"
    path.write_text(
        "<html><head><script>alert('x')</script><style>p{}</style></head>"
        "<body><h1>Dress code</h1><p>Hats are <b>not</b> permitted indoors.</p></body></html>"
    )
    text = extract_text(path)
    assert "Hats are not permitted indoors." in text.replace("\n", " ")
    assert "alert" not in text
    assert "<p>" not in text


def test_docx(tmp_path):
    import docx

    path = tmp_path / "minutes.docx"
    d = docx.Document()
    d.add_paragraph("The board approved the 2026-27 bell schedule.")
    d.save(path)
    assert "approved the 2026-27 bell schedule" in extract_text(path)


def test_pdf(tmp_path):
    path = tmp_path / "policy.pdf"
    path.write_bytes(minimal_pdf("Buses depart at 2:45 PM sharp."))
    assert "Buses depart at 2:45 PM sharp." in extract_text(path)


def test_unsupported_extension(tmp_path):
    path = tmp_path / "grades.xlsx"
    path.write_bytes(b"not really a spreadsheet")
    with pytest.raises(UnsupportedFormat):
        extract_text(path)
