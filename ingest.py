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
import logging
from pathlib import Path

from ingestion.chunker import chunk_documents
from ingestion.extractor import extract_from_chunks
from ingestion.loader import load_pdfs


if __name__ == "__main__":


    Path("logs").mkdir(exist_ok=True)

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
    extractions = extract_from_chunks(chunks)

    print(f"chunks: {len(chunks)}")
    print(f"extractions: {len(extractions)}")

    if not chunks:
        print("No chunks generated.")
        raise SystemExit(0)

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