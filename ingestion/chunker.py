# Text chunker for loaded PDF documents.
# Uses LangChain RecursiveCharacterTextSplitter to split documents into overlapping chunks.
# Chunk size and overlap should be configurable (defaults: 800 tokens, 150 overlap).
# Preserves and forwards all source metadata (source_file, page_number, doc_type) to each chunk.
# Returns a list of LangChain Document objects ready for entity extraction.

import logging
from typing import Sequence
from langchain_text_splitters import RecursiveCharacterTextSplitter

from langchain_core.documents import Document



logger = logging.getLogger(__name__)

DEFAULT_CHUNK_SIZE_TOKENS = 800
DEFAULT_CHUNK_OVERLAP_TOKENS = 150
DEFAULT_TOKEN_ENCODING = "cl100k_base"
DEFAULT_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]


def build_text_splitter(
    chunk_size_tokens: int = DEFAULT_CHUNK_SIZE_TOKENS,
    chunk_overlap_tokens: int = DEFAULT_CHUNK_OVERLAP_TOKENS,
    encoding_name: str = DEFAULT_TOKEN_ENCODING,
    separators: list[str] | None = None,
) -> RecursiveCharacterTextSplitter:
    """
    Build a token-aware RecursiveCharacterTextSplitter when possible.

    Falls back to an approximate character-based splitter if tiktoken
    or token-aware splitting is unavailable.
    """
    if chunk_size_tokens <= 0:
        raise ValueError("chunk_size_tokens must be > 0")

    if chunk_overlap_tokens < 0:
        raise ValueError("chunk_overlap_tokens must be >= 0")

    if chunk_overlap_tokens >= chunk_size_tokens:
        raise ValueError("chunk_overlap_tokens must be smaller than chunk_size_tokens")

    separators = separators or DEFAULT_SEPARATORS

    try:
        splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
            encoding_name=encoding_name,
            chunk_size=chunk_size_tokens,
            chunk_overlap=chunk_overlap_tokens,
            separators=separators,
            keep_separator=True,
            strip_whitespace=True,
        )
        logger.info(
            "Initialized token-aware chunker (size=%s overlap=%s encoding=%s)",
            chunk_size_tokens,
            chunk_overlap_tokens,
            encoding_name,
        )
        return splitter
    except Exception as exc:
        approx_chunk_size_chars = chunk_size_tokens * 4
        approx_chunk_overlap_chars = chunk_overlap_tokens * 4

        logger.warning(
            "Token-aware chunker unavailable; falling back to approximate "
            "character-based splitting (size=%s overlap=%s). Error: %s",
            approx_chunk_size_chars,
            approx_chunk_overlap_chars,
            exc,
        )

        return RecursiveCharacterTextSplitter(
            chunk_size=approx_chunk_size_chars,
            chunk_overlap=approx_chunk_overlap_chars,
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
    encoding_name: str = DEFAULT_TOKEN_ENCODING,
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
            encoding_name=encoding_name,
            separators=separators,
        )

    text = (document.page_content or "").strip()
    if not text:
        logger.debug("Skipping empty document during chunking")
        return []

    base_metadata = dict(document.metadata or {})
    raw_chunks = splitter.split_text(text)

    chunk_docs: list[Document] = []
    total_chunks = len(raw_chunks)

    for chunk_index, chunk_text in enumerate(raw_chunks, start=1):
        cleaned_chunk = chunk_text.strip()
        if not cleaned_chunk:
            continue

        metadata = {
            **base_metadata,
            "chunk_index": chunk_index,
            "chunk_count": total_chunks,
            "chunk_id": _make_chunk_id(base_metadata, chunk_index),
        }

        chunk_docs.append(
            Document(
                page_content=cleaned_chunk,
                metadata=metadata,
            )
        )

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
    encoding_name: str = DEFAULT_TOKEN_ENCODING,
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
        encoding_name=encoding_name,
        separators=separators,
    )

    all_chunks: list[Document] = []

    logger.info(
        "Starting chunking for %s source documents (size=%s overlap=%s)",
        len(documents),
        chunk_size_tokens,
        chunk_overlap_tokens,
    )

    for document in documents:
        all_chunks.extend(chunk_single_document(document=document, splitter=splitter))

    logger.info(
        "Finished chunking: input_documents=%s output_chunks=%s",
        len(documents),
        len(all_chunks),
    )

    return all_chunks