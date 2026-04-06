"""Idempotent Neo4j client for rag.

Provides a lightweight wrapper around the official neo4j driver with helpers
for common operations used by the ingestion and query pipeline:
- connection management
- run_query
- find_nodes
- upsert_node (idempotent by `id`)
- upsert_relationship (idempotent by `id`)
- ingestion metadata helper

The implementation favors clarity and testability; the driver is created in __init__
and methods return plain Python structures (lists/dicts) to ease mocking in tests.
"""

from typing import Any, Dict, Iterable, List, Optional
import os
import time
import logging

try:
    from neo4j import GraphDatabase
except Exception:  # pragma: no cover - allow tests to import without driver installed
    GraphDatabase = None

from .models import NodeModel, RelationshipModel

logger = logging.getLogger(__name__)


def _retry(fn, retries: int = 3, backoff: float = 0.5):
    """Simple retry wrapper for transient Neo4j errors."""

    def wrapper(*args, **kwargs):
        last_exc = None
        for attempt in range(1, retries + 1):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                last_exc = e
                logger.debug("Attempt %s/%s failed: %s", attempt, retries, e)
                if attempt < retries:
                    time.sleep(backoff * attempt)
        # re-raise last exception
        raise last_exc

    return wrapper


class Neo4jClient:
    """Lightweight Neo4j client wrapper.

    Parameters may be provided explicitly or via environment variables:
    - NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
    """

    def __init__(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        max_retries: int = 3,
    ) -> None:
        uri = uri or os.getenv("NEO4J_URI")
        user = user or os.getenv("NEO4J_USER")
        password = password or os.getenv("NEO4J_PASSWORD")
        if GraphDatabase is None:
            logger.warning("neo4j driver not available; Neo4jClient will not establish connections in this environment")
            self._driver = None
        else:
            self._driver = GraphDatabase.driver(uri, auth=(user, password))
        self._max_retries = max_retries

    def close(self) -> None:
        if self._driver:
            self._driver.close()

    def run_query(self, cypher: str, params: Optional[Dict[str, Any]] = None, db: Optional[str] = None) -> List[Dict[str, Any]]:
        """Run an arbitrary cypher query and return list of dicts.

        Results are converted to plain dictionaries mapping keys->values.
        """
        params = params or {}

        def _run():
            if not self._driver:
                raise RuntimeError("Neo4j driver not initialized")
            with self._driver.session() as session:
                res = session.run(cypher, params)
                return [dict(r.items()) for r in res]

        return _retry(_run, retries=self._max_retries)()

    def find_nodes(self, label: Optional[str] = None, property_filters: Optional[Dict[str, Any]] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Find nodes by label and property filters. Returns list of node property dicts.

        Example: find_nodes('Drug', {'name': 'ibuprofen'})
        """
        property_filters = property_filters or {}
        where_clauses = []
        params: Dict[str, Any] = {}
        for i, (k, v) in enumerate(property_filters.items()):
            param_name = f"p{i}"
            where_clauses.append(f"n.{k} = ${param_name}")
            params[param_name] = v
        where = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        label_clause = f":" + label if label else ""
        limit_clause = f"LIMIT {int(limit)}" if limit else ""
        cypher = f"MATCH (n{label_clause}) {where} RETURN n {{ .* }} as node {limit_clause}"
        rows = self.run_query(cypher, params)
        return [r["node"] for r in rows]

    def upsert_node(self, node: NodeModel) -> Dict[str, Any]:
        """Idempotently create or update a node based on node.id.

        Sets provided properties and preserves others.
        Returns the merged node properties.
        """
        labels = ":".join(node.labels) if node.labels else ""
        # ensure id is in params
        params = {"id": node.id, "props": node.properties}
        cypher = f"MERGE (n:{labels} {{id: $id}}) SET n += $props RETURN n {{ .* }} as node"

        rows = self.run_query(cypher, params)
        return rows[0]["node"] if rows else {}

    def upsert_relationship(self, rel: RelationshipModel) -> Dict[str, Any]:
        """Idempotently create or update a relationship by rel.id.

        The start and end nodes must already exist (or be created elsewhere). This method
        will MERGE the relationship between nodes identified by their `id` properties.
        Returns the merged relationship properties.
        """
        params = {"id": rel.id, "start_id": rel.start_id, "end_id": rel.end_id, "props": rel.properties}
        # Build cypher dynamically to place relationship type
        rel_type = rel.rel_type or "RELATED_TO"
        cypher = (
            "MATCH (a {id: $start_id}), (b {id: $end_id}) "
            f"MERGE (a)-[r:{rel_type} {{id: $id}}]->(b) SET r += $props RETURN r {{ .* }} as rel"
        )
        rows = self.run_query(cypher, params)
        return rows[0]["rel"] if rows else {}

    def record_ingestion_metadata(self, ingestion_id: str, doc_id: Optional[str] = None, chunk_id: Optional[str] = None, extra: Optional[Dict[str, Any]] = None) -> None:
        """Store a small ingestion metadata node linked to a Document node for auditing.

        Creates (or updates) a :Ingestion node and links it to a :Document (by doc_id) if provided.
        """
        extra = extra or {}
        params = {"ingestion_id": ingestion_id, "extra": extra}
        if doc_id:
            params["doc_id"] = doc_id
            cypher = (
                "MERGE (i:Ingestion {id: $ingestion_id}) SET i += $extra "
                "MERGE (d:Document {id: $doc_id}) "
                "MERGE (d)-[:INGESTED_BY]->(i) RETURN i { .* } as ingestion"
            )
        else:
            cypher = "MERGE (i:Ingestion {id: $ingestion_id}) SET i += $extra RETURN i { .* } as ingestion"
        try:
            self.run_query(cypher, params)
        except Exception as e:
            logger.exception("Failed to record ingestion metadata: %s", e)


# Simple context manager support
class Neo4jClientContext:
    def __init__(self, *args, **kwargs):
        self.client = Neo4jClient(*args, **kwargs)

    def __enter__(self):
        return self.client

    def __exit__(self, exc_type, exc, tb):
        self.client.close()


