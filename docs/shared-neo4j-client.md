# Shared — Neo4j Client (`shared/neo4j_client.py`)

[← Overview](./ingestion-overview.md)

## Purpose

Singleton Neo4j driver with connection retry logic.

## Configuration

```bash
NEO4J_URI=bolt://localhost:7687   # default
NEO4J_USER=neo4j
NEO4J_PASSWORD=yourpassword
```

## Usage

```python
from shared.neo4j_client import get_driver

driver = get_driver()
with driver.session() as session:
    result = session.run("MATCH (n) RETURN count(n)")
```

## Retry Logic

`get_driver(retries=5, delay=3.0)`

- Attempts connection up to `retries` times.
- Waits `delay` seconds between attempts.
- Calls `driver.verify_connectivity()` after each attempt.
- Raises `RuntimeError` if all retries are exhausted.

The driver is cached after the first successful connection (singleton pattern).
