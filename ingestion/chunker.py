# Text chunker for loaded PDF documents.
# Uses LangChain RecursiveCharacterTextSplitter to split documents into overlapping chunks.
# Uses approximate character-based splitting (4 chars ≈ 1 token).
# Preserves and forwards all source metadata (source_file, page_number, doc_type) to each chunk.
# Returns a list of LangChain Document objects ready for entity extraction.
from __future__ import annotations

import logging
from typing import Sequence
from langchain_text_splitters import RecursiveCharacterTextSplitter

from langchain_core.documents import Document
from ingestion.section_splitter import annotate_pages



logger = logging.getLogger(__name__)

CHARS_PER_TOKEN = 4
DEFAULT_CHUNK_SIZE_TOKENS = 800
DEFAULT_CHUNK_OVERLAP_TOKENS = 150
DEFAULT_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]


def build_text_splitter(
    chunk_size_tokens: int = DEFAULT_CHUNK_SIZE_TOKENS,
    chunk_overlap_tokens: int = DEFAULT_CHUNK_OVERLAP_TOKENS,
    separators: list[str] | None = None,
) -> RecursiveCharacterTextSplitter:
    """
    Build a character-based RecursiveCharacterTextSplitter.

    Converts token counts to approximate character counts (4 chars ≈ 1 token).
    """
    if chunk_size_tokens <= 0:
        raise ValueError("chunk_size_tokens must be > 0")

    if chunk_overlap_tokens < 0:
        raise ValueError("chunk_overlap_tokens must be >= 0")

    if chunk_overlap_tokens >= chunk_size_tokens:
        raise ValueError("chunk_overlap_tokens must be smaller than chunk_size_tokens")

    separators = separators or DEFAULT_SEPARATORS

    chunk_size_chars = chunk_size_tokens * CHARS_PER_TOKEN
    chunk_overlap_chars = chunk_overlap_tokens * CHARS_PER_TOKEN

    logger.info(
        "Initialized chunker (size=%s chars ≈ %s tokens, overlap=%s chars ≈ %s tokens)",
        chunk_size_chars,
        chunk_size_tokens,
        chunk_overlap_chars,
        chunk_overlap_tokens,
    )

    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size_chars,
        chunk_overlap=chunk_overlap_chars,
        separators=separators,
        keep_separator=True,
        strip_whitespace=True,
    )


def _make_chunk_id(metadata: dict, chunk_index: int) -> str:
    source_file = metadata.get("source_file", "unknown")
    page_number = metadata.get("page_number", "?")
    return f"{source_file}:p{page_number}:c{chunk_index}"


def chunk_single_document(
    document: Document,
    splitter: RecursiveCharacterTextSplitter | None = None,
    chunk_size_tokens: int = DEFAULT_CHUNK_SIZE_TOKENS,
    chunk_overlap_tokens: int = DEFAULT_CHUNK_OVERLAP_TOKENS,
    separators: list[str] | None = None,
) -> list[Document]:
    """
    Split one LangChain Document into overlapping chunks.

    Preserves all original metadata and adds:
    - chunk_index
    - chunk_count
    - chunk_id
    """
    if splitter is None:
        splitter = build_text_splitter(
            chunk_size_tokens=chunk_size_tokens,
            chunk_overlap_tokens=chunk_overlap_tokens,
            separators=separators,
        )

    text = (document.page_content or "").strip()
    if not text:
        logger.debug("Skipping empty document during chunking")
        return []

    base_metadata = dict(document.metadata or {})
    raw_chunks = splitter.split_text(text)

    chunk_docs: list[Document] = []

    for chunk_index, chunk_text in enumerate(raw_chunks, start=1):
        cleaned_chunk = chunk_text.strip()
        if not cleaned_chunk:
            continue

        metadata = {
            **base_metadata,
            "chunk_index": chunk_index,
            "chunk_id": _make_chunk_id(base_metadata, chunk_index),
        }

        chunk_docs.append(
            Document(
                page_content=cleaned_chunk,
                metadata=metadata,
            )
        )

    # Backfill chunk_count now that empty chunks have been filtered.
    for doc in chunk_docs:
        doc.metadata["chunk_count"] = len(chunk_docs)

    logger.info(
        "Chunked document source_file=%s page_number=%s chunks=%s",
        base_metadata.get("source_file"),
        base_metadata.get("page_number"),
        len(chunk_docs),
    )

    return chunk_docs


def chunk_documents(
    documents: Sequence[Document],
    chunk_size_tokens: int = DEFAULT_CHUNK_SIZE_TOKENS,
    chunk_overlap_tokens: int = DEFAULT_CHUNK_OVERLAP_TOKENS,
    separators: list[str] | None = None,
) -> list[Document]:
    """
    Split a list of loaded page-level Documents into chunk-level Documents.

    Returns a flat list of LangChain Document objects ready for entity extraction.
    """
    if not documents:
        logger.warning("No documents provided to chunk_documents")
        return []

    splitter = build_text_splitter(
        chunk_size_tokens=chunk_size_tokens,
        chunk_overlap_tokens=chunk_overlap_tokens,
        separators=separators,
    )

    all_chunks: list[Document] = []

    logger.info(
        "Starting chunking for %s source documents (size=%s overlap=%s)",
        len(documents),
        chunk_size_tokens,
        chunk_overlap_tokens,
    )

    # Group pages by source_file so propagation resets between PDFs.
    # Without grouping, last_known bleeds from the final section of one PDF
    # into the opening unknown pages of the next PDF.
    groups: dict[str, list[Document]] = {}
    for doc in documents:
        key = doc.metadata.get("source_file", "")
        groups.setdefault(key, []).append(doc)

    for source_file, group in groups.items():
        annotate_pages(group, propagate=True)
        logger.debug("Annotated %d pages for %s", len(group), source_file)

    for document in documents:
        all_chunks.extend(chunk_single_document(document=document, splitter=splitter))

    logger.info(
        "Finished chunking: input_documents=%s output_chunks=%s",
        len(documents),
        len(all_chunks),
    )

    return all_chunks
