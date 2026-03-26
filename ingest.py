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
from ingestion.loader import load_pdfs
from ingestion.chunker import chunk_documents
import logging
from pathlib import Path
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
    print(len(docs))
    print(docs[0].metadata)
    print(docs[0].page_content[:300])

    chunks = chunk_documents(docs)

    print(f"pages: {len(docs)}")
    print(f"chunks: {len(chunks)}")
    print(f"-" * 50)
    print(chunks[0].metadata)
    print(chunks[1].metadata)
    print(f"-" * 50)
    print(chunks[1].page_content[:300])