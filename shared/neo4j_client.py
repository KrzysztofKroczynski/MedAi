# Shared Neo4j driver singleton.
# Reads NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD from environment variables.
# Exposes a get_driver() function that returns a connected neo4j.GraphDatabase.driver instance.
# Should handle connection retries on startup (Neo4j may still be initializing).

import os
import time
import logging
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_driver = None

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")


def get_driver(retries: int = 5, delay: float = 3.0):
    """Return a connected Neo4j driver, retrying if Neo4j is still initializing."""
    global _driver
    if _driver is not None:
        return _driver

    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
            driver.verify_connectivity()
            _driver = driver
            logger.info("Connected to Neo4j at %s", NEO4J_URI)
            return _driver
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "Neo4j not ready (attempt %d/%d): %s — retrying in %.0fs",
                attempt, retries, exc, delay,
            )
            if attempt < retries:
                time.sleep(delay)

    raise RuntimeError(
        f"Could not connect to Neo4j at {NEO4J_URI} after {retries} attempts"
    ) from last_exc
