# CLI entrypoint for the ingestion pipeline.
# Orchestrates the full ingestion flow in order:
#   1. graph/schema.py   — apply Neo4j constraints and indexes
#   2. ingestion/loader.py  — load all PDFs from data/pdfs/
#   3. ingestion/chunker.py — split documents into chunks
#   4. ingestion/extractor.py — extract entities and relations from each chunk via GPT-4o
#   5. graph/graph_builder.py — write results into Neo4j
# Logs progress and errors to logs/ directory.
# Should be idempotent: safe to re-run after adding new PDFs (MERGE prevents duplicates).

# TODO: TESTING ONLY
import json
import logging
from pathlib import Path
from typing import Any

from graph.schema import apply
from ingestion.chunker import chunk_documents
from ingestion.extractor import extract_from_chunks
from ingestion.loader import load_pdfs


def _load_cached_extractions(cache_path: Path, logger: logging.Logger) -> list[dict[str, Any]] | None:
    """Load cached extraction results if cache exists and contains data."""
    if not cache_path.exists():
        return None

    try:
        with cache_path.open("r", encoding="utf-8") as fp:
            data = json.load(fp)
    except Exception as exc:
        logger.warning("Could not read extraction cache %s: %s", cache_path, exc)
        return None

    if not isinstance(data, list) or not data:
        logger.info("Extraction cache found but empty/invalid at %s. Recomputing.", cache_path)
        return None

    cached = [item for item in data if isinstance(item, dict)]
    if not cached:
        logger.info("Extraction cache has no valid entries at %s. Recomputing.", cache_path)
        return None

    logger.info("Loaded %s cached extraction results from %s", len(cached), cache_path)
    return cached


def _save_extractions_cache(cache_path: Path, extractions: list[dict[str, Any]], logger: logging.Logger) -> None:
    """Persist extraction results to JSON cache file."""
    try:
        with cache_path.open("w", encoding="utf-8") as fp:
            json.dump(extractions, fp, ensure_ascii=False, indent=2)
        logger.info("Saved %s extraction results to %s", len(extractions), cache_path)
    except Exception as exc:
        logger.warning("Could not write extraction cache %s: %s", cache_path, exc)


if __name__ == "__main__":
    apply()


    Path("logs").mkdir(exist_ok=True)
    processed_dir = Path("data/processed")
    processed_dir.mkdir(parents=True, exist_ok=True)
    extraction_cache_path = processed_dir / "extractions.json"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("logs/app.log", encoding="utf-8"),
        ],
    )

    logger = logging.getLogger(__name__)
    logger.info("App started")

    docs = load_pdfs()
    print(f"pages: {len(docs)}")

    if not docs:
        print("No PDF pages loaded. Put PDF files under data/pdfs and re-run.")
        raise SystemExit(0)

    print("sample page metadata:")
    print(docs[0].metadata)
    print("sample page content:")
    print(docs[0].page_content[:300])

    chunks = chunk_documents(docs)

    print(f"chunks: {len(chunks)}")

    if not chunks:
        print("No chunks generated.")
        raise SystemExit(0)

    extractions = _load_cached_extractions(extraction_cache_path, logger)
    if extractions is None:
        extractions = extract_from_chunks(chunks)
        _save_extractions_cache(extraction_cache_path, extractions, logger)

    print(f"extractions: {len(extractions)}")

    print(f"-" * 50)
    print(chunks[0].metadata)
    if len(chunks) > 1:
        print(chunks[1].metadata)
    print(f"-" * 50)
    print(chunks[0].page_content[:300])

    if extractions:
        first = extractions[0]
        print(f"-" * 50)
        print("sample extraction metadata:")
        print(first.get("metadata", {}))
        print("sample entities:")
        print(first.get("entities", [])[:5])
        print("sample relations:")
        print(first.get("relations", [])[:5])