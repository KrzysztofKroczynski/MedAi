# PDF loader for medication documents.
# Uses LangChain PyPDFLoader to load each PDF from the data/pdfs/ directory.
# For each page, attaches metadata: { source_file, page_number, doc_type }.
# doc_type is inferred from filename keywords (e.g. "PIL", "SmPC").
# Returns a flat list of LangChain Document objects across all PDFs.
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Iterable

from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document

logger = logging.getLogger(__name__)

DEFAULT_PDF_DIR = "data/pdfs"

DOC_TYPE_RULES: tuple[tuple[str, str], ...] = (
    ("smpc", "SmPC"),
    ("summary-of-product-characteristics", "SmPC"),
    ("summary_of_product_characteristics", "SmPC"),
    ("characteristics", "SmPC"),
    ("pil", "PIL"),
    ("leaflet", "PIL"),
    ("ulotka", "PIL"),
    ("package-insert", "PIL"),
    ("package_insert", "PIL"),
    ("prescribing", "PrescribingInformation"),
    ("interaction", "InteractionReference"),
    ("interactions", "InteractionReference"),
    ("formulary", "Formulary"),
)


def resolve_doc_type(filename: str) -> str:
    """
    Resolve document type from filename keywords.

    Examples:
    - ibuprofen_PIL.pdf -> PIL
    - paracetamol_SmPC.pdf -> SmPC
    """
    lowered = filename.lower()

    for keyword, doc_type in DOC_TYPE_RULES:
        if keyword in lowered:
            return doc_type

    return "Unknown"


def resolve_pdf_dir(pdf_dir: str | Path | None = None) -> Path:
    """
    Resolve the PDF directory.

    Priority:
    1. explicit function argument
    2. PDF_DIR environment variable
    3. default: data/pdfs
    """
    raw_path = pdf_dir or os.getenv("PDF_DIR", DEFAULT_PDF_DIR)
    return Path(raw_path).expanduser().resolve()


def iter_pdf_files(pdf_dir: Path, recursive: bool = True) -> Iterable[Path]:
    """
    Yield PDF files in deterministic order.
    """
    pattern = "**/*.pdf" if recursive else "*.pdf"
    yield from sorted(
        path for path in pdf_dir.glob(pattern) if path.is_file()
    )


def load_single_pdf(pdf_path: str | Path) -> list[Document]:
    """
    Load a single PDF into page-level LangChain Documents.

    Adds/normalizes metadata:
    - source_file
    - page_number (1-based)
    - doc_type
    - source_path
    """
    pdf_path = Path(pdf_path).resolve()

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file does not exist: {pdf_path}")

    doc_type = resolve_doc_type(pdf_path.name)
    loader = PyPDFLoader(str(pdf_path))
    page_docs = loader.load()

    normalized_docs: list[Document] = []
    skipped_blank_pages = 0

    for fallback_page_idx, doc in enumerate(page_docs, start=1):
        text = (doc.page_content or "").strip()
        if not text:
            skipped_blank_pages += 1
            continue

        original_metadata = dict(doc.metadata or {})

        raw_page = original_metadata.get("page")
        if isinstance(raw_page, int):
            page_number = raw_page + 1
        else:
            page_number = fallback_page_idx

        merged_metadata = {
            **original_metadata,
            "source_file": pdf_path.name,
            "page_number": page_number,
            "doc_type": doc_type,
            "source_path": str(pdf_path),
        }

        normalized_docs.append(
            Document(
                page_content=text,
                metadata=merged_metadata,
            )
        )

    logger.info(
        "Loaded %s non-empty pages from %s (doc_type=%s, skipped_blank_pages=%s)",
        len(normalized_docs),
        pdf_path.name,
        doc_type,
        skipped_blank_pages,
    )

    return normalized_docs


def load_pdfs(
    pdf_dir: str | Path | None = None,
    recursive: bool = True,
    fail_fast: bool = False,
) -> list[Document]:
    """
    Load all PDFs from a directory into a flat list of page-level Documents.

    Args:
        pdf_dir: Directory containing PDFs. Defaults to data/pdfs or PDF_DIR env var.
        recursive: Whether to search subdirectories.
        fail_fast: If True, stop on first broken PDF. If False, log and continue.

    Returns:
        Flat list of LangChain Document objects across all PDFs.
    """
    resolved_dir = resolve_pdf_dir(pdf_dir)

    if not resolved_dir.exists():
        raise FileNotFoundError(f"PDF directory does not exist: {resolved_dir}")

    if not resolved_dir.is_dir():
        raise NotADirectoryError(f"Expected a directory, got: {resolved_dir}")

    pdf_files = list(iter_pdf_files(resolved_dir, recursive=recursive))

    if not pdf_files:
        logger.warning("No PDF files found in %s", resolved_dir)
        return []

    all_docs: list[Document] = []
    failed_files: list[str] = []

    logger.info("Starting PDF load from %s (%s files found)", resolved_dir, len(pdf_files))

    for pdf_file in pdf_files:
        try:
            docs = load_single_pdf(pdf_file)
            all_docs.extend(docs)
        except Exception:
            failed_files.append(pdf_file.name)
            logger.exception("Failed to load PDF: %s", pdf_file)
            if fail_fast:
                raise

    logger.info(
        "Finished loading PDFs: files=%s, failed=%s, total_documents=%s",
        len(pdf_files),
        len(failed_files),
        len(all_docs),
    )

    if failed_files:
        logger.warning("Some PDFs failed to load: %s", ", ".join(failed_files))

    return all_docs