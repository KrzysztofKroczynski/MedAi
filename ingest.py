"""
Ingestion pipeline: PDF extraction only.
Reads PDFs from data/pdfs/, extracts entities and relations via LLM,
and saves results to data/processed/extractions.json.

Run seed.py afterwards to load the cache into Neo4j.
Safe to re-run — overwrites the cache with fresh extractions.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from ingestion.chunker import chunk_documents
from ingestion.extractor import extract_from_chunks
from ingestion.loader import load_pdfs

if __name__ == "__main__":
    Path("logs").mkdir(exist_ok=True)
    processed_dir = Path("data/processed")
    processed_dir.mkdir(parents=True, exist_ok=True)
    cache_path = processed_dir / "extractions.json"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("logs/ingest.log", encoding="utf-8"),
        ],
    )
    logger = logging.getLogger(__name__)
    logger.info("Ingestion started")

    docs = load_pdfs()
    logger.info("Loaded %d pages from PDFs", len(docs))

    if not docs:
        logger.error("No PDF pages loaded. Place PDF files under data/pdfs/ and re-run.")
        raise SystemExit(1)

    chunks = chunk_documents(docs)
    logger.info("Generated %d chunks", len(chunks))

    if not chunks:
        logger.error("No chunks generated.")
        raise SystemExit(1)

    extractions = extract_from_chunks(chunks)
    logger.info("Extracted %d results", len(extractions))

    try:
        with cache_path.open("w", encoding="utf-8") as fp:
            json.dump(extractions, fp, ensure_ascii=False, indent=2)
        logger.info("Saved extractions to %s", cache_path)
    except Exception as exc:
        logger.error("Failed to write extraction cache: %s", exc)
        raise SystemExit(1)

    logger.info("Ingestion complete. Run seed.py to load into Neo4j.")
