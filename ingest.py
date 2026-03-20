# CLI entrypoint for the ingestion pipeline.
# Orchestrates the full ingestion flow in order:
#   1. graph/schema.py   — apply Neo4j constraints and indexes
#   2. ingestion/loader.py  — load all PDFs from data/pdfs/
#   3. ingestion/chunker.py — split documents into chunks
#   4. ingestion/extractor.py — extract entities and relations from each chunk via GPT-4o
#   5. graph/graph_builder.py — write results into Neo4j
# Logs progress and errors to logs/ directory.
# Should be idempotent: safe to re-run after adding new PDFs (MERGE prevents duplicates).
