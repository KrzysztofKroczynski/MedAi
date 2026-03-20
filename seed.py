# Seed script: loads pre-processed graph data from data/processed/ into Neo4j.
# Schema constraints are applied before this script runs (see docker-compose.yml).
# Reads all JSON files from data/processed/ — each file contains the extraction
# output for one PDF: { "entities": [...], "relations": [...] }.
# Calls graph/graph_builder.py to write nodes and edges.
# If data/processed/ is empty or missing, logs a warning and exits cleanly (does not crash).
# Safe to re-run — uses MERGE so no duplicate data is created.
# This script is the Docker startup alternative to running the full ingestion pipeline.
# Ingestion pipeline (ingest.py) saves its extraction output to data/processed/,
# so those files can be committed and reused across environments without re-running GPT-4o.
