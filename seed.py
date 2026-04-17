"""
Seed script: loads extraction cache into Neo4j.
Reads data/processed/extractions.json produced by ingest.py,
applies schema constraints, then writes nodes and edges.

Safe to re-run — uses MERGE so no duplicates are created.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from graph.graph_builder import write_extractions
from graph.schema import apply, reset

if __name__ == "__main__":
    Path("logs").mkdir(exist_ok=True)
    cache_path = Path("data/processed/extractions.json")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("logs/seed.log", encoding="utf-8"),
        ],
    )
    logger = logging.getLogger(__name__)
    logger.info("Seed started")

    if not cache_path.exists():
        logger.error("No extraction cache found at %s. Run ingest.py first.", cache_path)
        raise SystemExit(1)

    try:
        with cache_path.open("r", encoding="utf-8") as fp:
            extractions = json.load(fp)
    except Exception as exc:
        logger.error("Failed to read extraction cache: %s", exc)
        raise SystemExit(1)

    if not extractions:
        logger.error("Extraction cache is empty. Re-run ingest.py.")
        raise SystemExit(1)

    logger.info("Loaded %d extraction results from cache", len(extractions))

    reset()
    logger.info("Graph reset")

    apply()
    logger.info("Schema applied")

    stats = write_extractions(extractions)
    logger.info(
        "Graph persisted: records=%s nodes=%s relations=%s failed=%s",
        stats["records"],
        stats["nodes"],
        stats["relations"],
        stats["failed"],
    )
    logger.info("Seed complete.")
