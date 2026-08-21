"""Unit tests for PDF text extraction (Sprint 3.1).

Uses PyMuPDF to create real test PDFs so we test the actual extraction
pipeline, not just mocked interfaces.
"""

from __future__ import annotations

import fitz
import pytest

from app.documents.exceptions import DocumentUnsupportedError
from app.documents.pdf import PdfTextExtractor

_PDF_MIME = "application/pdf"


def _make_text_pdf(text: str) -> bytes:
    """Create a minimal text-based PDF using PyMuPDF."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    buf = doc.write()
    doc.close()
    return buf


def _make_empty_pdf() -> bytes:
    """Create a PDF with a single blank page."""
    doc = fitz.open()
    doc.new_page()
    buf = doc.write()
    doc.close()
    return buf


def _extract(extractor: PdfTextExtractor, data: bytes, filename: str) -> object:
    """Helper to call extract with the standard PDF mime type."""
    return __import__("asyncio").run(
        extractor.extract(data, filename=filename, mime_type=_PDF_MIME)
    )


@pytest.fixture
def extractor() -> PdfTextExtractor:
    return PdfTextExtractor(max_characters=100_000)


# ---------------------------------------------------------------------------
# 1. Normal text PDF
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_normal_text_pdf(extractor: PdfTextExtractor) -> None:
    """A simple text-based PDF extracts its content correctly."""
    pdf_bytes = _make_text_pdf("Hello World, this is a test PDF document.")
    result = await extractor.extract(
        pdf_bytes, filename="test.pdf", mime_type=_PDF_MIME
    )

    assert result.has_text
    assert "Hello World" in result.text
    assert result.page_count == 1
    assert result.character_count > 0
    assert result.extraction_method == "pymupdf"


# ---------------------------------------------------------------------------
# 2. Multi-page PDF
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_multipage_pdf(extractor: PdfTextExtractor) -> None:
    """Text from all pages is extracted in reading order."""
    doc = fitz.open()
    page1 = doc.new_page()
    page1.insert_text((72, 72), "First page content")
    page2 = doc.new_page()
    page2.insert_text((72, 72), "Second page content")
    pdf_bytes = doc.write()
    doc.close()

    result = await extractor.extract(
        pdf_bytes, filename="multi.pdf", mime_type=_PDF_MIME
    )

    assert result.has_text
    assert "First page content" in result.text
    assert "Second page content" in result.text
    assert result.page_count == 2
    assert result.text.index("First page") < result.text.index("Second page")


# ---------------------------------------------------------------------------
# 3. Empty PDF
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_empty_pdf(extractor: PdfTextExtractor) -> None:
    """A PDF with only blank pages returns has_text=False."""
    pdf_bytes = _make_empty_pdf()
    result = await extractor.extract(
        pdf_bytes, filename="empty.pdf", mime_type=_PDF_MIME
    )

    assert not result.has_text
    assert result.text == ""
    assert result.page_count == 1
    assert result.character_count == 0


# ---------------------------------------------------------------------------
# 4. Image-only / scanned PDF
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_image_only_pdf(extractor: PdfTextExtractor) -> None:
    """A PDF containing only images returns has_text=False."""
    doc = fitz.open()
    page = doc.new_page()
    rect = page.rect
    page.draw_rect(rect, color=(1, 0, 0), fill=(1, 0, 0))
    pdf_bytes = doc.write()
    doc.close()

    result = await extractor.extract(
        pdf_bytes, filename="image_only.pdf", mime_type=_PDF_MIME
    )

    assert not result.has_text
    assert result.error is not None


# ---------------------------------------------------------------------------
# 5. Malformed PDF
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_malformed_pdf(extractor: PdfTextExtractor) -> None:
    """Garbage bytes that aren't a valid PDF raise DocumentUnsupportedError."""
    with pytest.raises(DocumentUnsupportedError):
        await extractor.extract(
            b"Not a PDF at all", filename="bad.pdf", mime_type=_PDF_MIME
        )


# ---------------------------------------------------------------------------
# 6. Large PDF (truncation)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_large_pdf_truncates() -> None:
    """PDFs exceeding max_characters are truncated, with truncation recorded."""
    doc = fitz.open()
    for _ in range(10):
        page = doc.new_page()
        page.insert_text((72, 72), "A" * 500)
    pdf_bytes = doc.write()
    doc.close()

    small_extractor = PdfTextExtractor(max_characters=100)
    result = await small_extractor.extract(
        pdf_bytes, filename="large.pdf", mime_type=_PDF_MIME
    )

    assert result.has_text
    assert len(result.text) <= 100
    assert result.metadata.get("truncated") is True


# ---------------------------------------------------------------------------
# 7. Unicode text
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_unicode_text(extractor: PdfTextExtractor) -> None:
    """Unicode characters are extracted correctly."""
    unicode_text = "Café résumé naïve über"
    pdf_bytes = _make_text_pdf(unicode_text)
    result = await extractor.extract(
        pdf_bytes, filename="unicode.pdf", mime_type=_PDF_MIME
    )

    assert result.has_text
    assert "Café" in result.text
    assert "résumé" in result.text


# ---------------------------------------------------------------------------
# 8. Whitespace normalization
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_whitespace_normalization(extractor: PdfTextExtractor) -> None:
    """Excessive whitespace is normalized."""
    text = "Line 1\n\n\n\n\n\nLine 2     with    spaces"
    pdf_bytes = _make_text_pdf(text)
    result = await extractor.extract(
        pdf_bytes, filename="whitespace.pdf", mime_type=_PDF_MIME
    )

    assert result.has_text
    assert "\n\n\n" not in result.text


# ---------------------------------------------------------------------------
# 9. Empty bytes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_empty_bytes(extractor: PdfTextExtractor) -> None:
    """Empty byte input returns has_text=False without raising."""
    result = await extractor.extract(
        b"", filename="empty_bytes.pdf", mime_type=_PDF_MIME
    )

    assert not result.has_text
    assert result.text == ""
    assert result.page_count == 0


# ---------------------------------------------------------------------------
# 10. Extraction method name
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extraction_method_name(extractor: PdfTextExtractor) -> None:
    """The extractor reports its name."""
    assert extractor.extractor_name == "pymupdf"


# ---------------------------------------------------------------------------
# 11. Metadata contains filename
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_metadata_contains_filename(extractor: PdfTextExtractor) -> None:
    """Extracted metadata includes the original filename."""
    pdf_bytes = _make_text_pdf("Test content")
    result = await extractor.extract(
        pdf_bytes, filename="my_report.pdf", mime_type=_PDF_MIME
    )

    assert result.has_text
    assert result.metadata.get("filename") == "my_report.pdf"
