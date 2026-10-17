import pytest

from app.extraction.chunking import Block, hard_split, pack_blocks, paragraph_blocks
from app.extraction.models import ExtractionError, SourceRef
from app.extraction.parsers import parse_csv, parse_file, parse_text
from tests.conftest import make_docx, make_pdf


# ----------------------------------------------------------------- chunking
def test_paragraph_blocks_keep_line_numbers():
    blocks = paragraph_blocks(["a", "b", "", "", "c"], first_line_no=10)
    assert [(b.text, b.line_start, b.line_end) for b in blocks] == [("a\nb", 10, 11), ("c", 14, 14)]


def test_pack_blocks_merges_small_and_splits_large():
    small = [Block("x" * 100, 1, 1), Block("y" * 100, 3, 3)]
    packed = pack_blocks(small, max_chars=500)
    assert len(packed) == 1 and (packed[0].line_start, packed[0].line_end) == (1, 3)
    big = pack_blocks([Block("Sentence one. " * 200, 5, 9)], max_chars=300)
    assert len(big) > 1 and all(len(b.text) <= 300 for b in big)
    assert all((b.line_start, b.line_end) == (5, 9) for b in big)


def test_hard_split_handles_unbroken_text():
    assert all(len(p) <= 100 for p in hard_split("z" * 1000, 100))


def test_source_ref_labels():
    assert SourceRef(filename="a.pdf", page=3).label() == "a.pdf, page 3"
    assert SourceRef(filename="a.csv", row_start=4, row_end=9).label() == "a.csv, rows 4–9"
    assert SourceRef(filename="a.md", heading="Intro", line_start=2, line_end=2).label() == 'a.md, section "Intro", line 2'


# ----------------------------------------------------------------- text / markdown
def test_plain_text_lines_and_ids(tmp_path):
    f = tmp_path / "notes.txt"
    f.write_text("First paragraph.\nstill first.\n\nSecond paragraph.")
    doc = parse_file(f, "notes.txt", "d1")
    assert doc.doc_type == "txt"
    assert doc.chunks[0].chunk_id == "d1-c1"
    assert doc.chunks[0].source.line_start == 1 and doc.chunks[0].source.line_end == 4


def test_markdown_headings_tracked_and_code_fences_ignored():
    text = "# Plan\nIntro text\n\n## Budget\nWe have $5k.\n\n```\n# not a heading\n```\n\n## Risks\nNone listed."
    doc = parse_text(text, "plan.md", "d1", markdown=True)
    headings = [c.source.heading for c in doc.chunks]
    assert "Plan" in headings and "Plan > Budget" in headings and "Plan > Risks" in headings
    budget = next(c for c in doc.chunks if c.source.heading == "Plan > Budget")
    assert "not a heading" in budget.text  # fenced content stays in its section
    assert budget.source.line_start == 5


def test_latin1_text_decoded_with_warning(tmp_path):
    f = tmp_path / "old.txt"
    f.write_bytes("caf\xe9 budget".encode("latin-1"))
    doc = parse_file(f, "old.txt", "d1")
    assert "Windows-1252" in doc.warnings[0]


def test_empty_and_whitespace_files_rejected(tmp_path):
    for name, content in [("empty.txt", b""), ("blank.md", b"  \n\n ")]:
        f = tmp_path / name
        f.write_bytes(content)
        with pytest.raises(ExtractionError) as exc:
            parse_file(f, name, "d1")
        assert exc.value.code == "empty_document"


def test_binary_masquerading_as_text_rejected(tmp_path):
    f = tmp_path / "bin.txt"
    f.write_bytes(b"\x00\x01\x02binary\x00")
    with pytest.raises(ExtractionError) as exc:
        parse_file(f, "bin.txt", "d1")
    assert exc.value.code == "binary_content"


def test_unsupported_extension_rejected(tmp_path):
    f = tmp_path / "x.exe"
    f.write_bytes(b"MZ")
    with pytest.raises(ExtractionError) as exc:
        parse_file(f, "x.exe", "d1")
    assert exc.value.code == "unsupported_type"


# ----------------------------------------------------------------- csv
CSV = "name,amount,owner\nAlpha,100,Ann\nBeta,,Bob\nGamma,300,\n"


def test_csv_profile_and_row_numbers():
    doc = parse_csv(CSV.encode(), "budget.csv", "d1", max_rows=100)
    profile = doc.chunks[0]
    assert profile.kind == "dataset_profile" and profile.source.heading == "Dataset profile"
    assert "Data rows: 3" in profile.text
    assert "Column 'amount': 1 empty of 3" in profile.text
    assert "min=100" in profile.text and "max=300" in profile.text
    rows = doc.chunks[1]
    assert rows.source.row_start == 2 and rows.source.row_end == 4  # header is row 1
    assert "Row 3: name=Beta; owner=Bob" in rows.text  # empty amount omitted


def test_csv_semicolon_delimiter_detected():
    doc = parse_csv(b"a;b\n1;2\n3;4\n", "s.csv", "d1", max_rows=10)
    assert doc.metadata["columns"] == ["a", "b"]


def test_csv_ragged_and_truncation_warnings():
    data = "a,b\n1,2\n3\n4,5\n6,7\n".encode()
    doc = parse_csv(data, "r.csv", "d1", max_rows=3)
    joined = " ".join(doc.warnings)
    assert "Only the first 3 of 4" in joined and "different number of cells" in joined


def test_csv_header_only_and_empty_rejected():
    for data in (b"a,b\n", b"\n\n", b""):
        with pytest.raises(ExtractionError):
            parse_csv(data, "e.csv", "d1", max_rows=10)


def test_csv_large_splits_into_multiple_chunks():
    rows = "\n".join(f"{i},value number {i} with some padding text" for i in range(1, 400))
    doc = parse_csv(f"id,text\n{rows}\n".encode(), "big.csv", "d1", max_rows=1000)
    row_chunks = [c for c in doc.chunks if c.kind == "dataset_rows"]
    assert len(row_chunks) > 3
    assert row_chunks[0].source.row_start == 2
    assert row_chunks[-1].source.row_end == 400
    assert all(len(c.text) < 1500 for c in row_chunks)


# ----------------------------------------------------------------- pdf
def test_pdf_page_numbers_preserved(tmp_path):
    f = tmp_path / "spec.pdf"
    f.write_bytes(make_pdf(["Page one budget is five thousand dollars.", "Page two timeline is six weeks."]))
    doc = parse_file(f, "spec.pdf", "d1")
    assert doc.doc_type == "pdf" and doc.metadata["pages"] == 2
    by_page = {c.source.page: c.text for c in doc.chunks}
    assert "budget" in by_page[1] and "timeline" in by_page[2]


def test_pdf_without_text_rejected(tmp_path):
    f = tmp_path / "scan.pdf"
    f.write_bytes(make_pdf([""]))
    with pytest.raises(ExtractionError) as exc:
        parse_file(f, "scan.pdf", "d1")
    assert exc.value.code == "no_extractable_text"


def test_malformed_pdf_rejected(tmp_path):
    f = tmp_path / "bad.pdf"
    f.write_bytes(b"%PDF-1.4 this is not really a pdf at all")
    with pytest.raises(ExtractionError) as exc:
        parse_file(f, "bad.pdf", "d1")
    assert exc.value.code in {"malformed_pdf", "no_extractable_text"}


def test_pdf_extension_with_wrong_content_rejected(tmp_path):
    f = tmp_path / "fake.pdf"
    f.write_bytes(b"just some text")
    with pytest.raises(ExtractionError) as exc:
        parse_file(f, "fake.pdf", "d1")
    assert exc.value.code == "content_mismatch"


# ----------------------------------------------------------------- docx
def test_docx_headings_and_tables(tmp_path):
    def build(doc):
        doc.add_heading("Project Alpha", level=1)
        doc.add_paragraph("Overview paragraph.")
        doc.add_heading("Budget", level=2)
        doc.add_paragraph("Total budget is limited.")
        table = doc.add_table(rows=2, cols=2)
        table.cell(0, 0).text, table.cell(0, 1).text = "Item", "Cost"
        table.cell(1, 0).text, table.cell(1, 1).text = "Hosting", "$200"

    f = tmp_path / "plan.docx"
    f.write_bytes(make_docx(build))
    doc = parse_file(f, "plan.docx", "d1")
    headings = {c.source.heading for c in doc.chunks}
    assert "Project Alpha" in headings and "Project Alpha > Budget" in headings
    budget = next(c for c in doc.chunks if c.source.heading == "Project Alpha > Budget")
    assert "Hosting | $200" in budget.text


def test_malformed_docx_rejected(tmp_path):
    f = tmp_path / "bad.docx"
    f.write_bytes(b"PK\x03\x04 definitely not a real zip file")
    with pytest.raises(ExtractionError) as exc:
        parse_file(f, "bad.docx", "d1")
    assert exc.value.code == "malformed_docx"


def test_docx_with_wrong_magic_rejected(tmp_path):
    f = tmp_path / "text.docx"
    f.write_text("plain text pretending to be word")
    with pytest.raises(ExtractionError) as exc:
        parse_file(f, "text.docx", "d1")
    assert exc.value.code == "content_mismatch"


def test_empty_docx_rejected(tmp_path):
    f = tmp_path / "empty.docx"
    f.write_bytes(make_docx(lambda d: None))
    with pytest.raises(ExtractionError) as exc:
        parse_file(f, "empty.docx", "d1")
    assert exc.value.code == "empty_document"
