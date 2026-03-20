# Seed script: loads pre-processed graph data from data/processed/ into Neo4j.
# Reads all JSON files from data/processed/ — each file contains the extraction
# output for one PDF: { "entities": [...], "relations": [...] }.
# Calls graph/schema.py to apply constraints, then graph/graph_builder.py to write nodes and edges.
# If data/processed/ is empty or missing, logs a warning and exits cleanly (does not crash).
# Safe to re-run — uses MERGE so no duplicate data is created.
# This script is the Docker startup alternative to running the full ingestion pipeline.
# Ingestion pipeline (ingest.py) should save its output to data/processed/ in addition to Neo4j,
# so the processed files can be committed and reused across environments.
