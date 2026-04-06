"""High-level ingestion pipeline for GraphRAG.

Responsibilities:
- ingest_chunks(chunks, extractor, neo4j_client, ingestion_id=None)
  where chunks is an iterable of dicts: {"text": ..., "doc_id": ..., "chunk_id": ...}
- performs extraction, upserts nodes and relationships idempotently
- records ingestion metadata and returns a compact report

The implementation is synchronous and easily testable by passing mocks for the extractor and Neo4j client.
"""

from typing import Dict, Iterable, List, Optional
import uuid
import logging

from .models import ExtractionResult, NodeModel, RelationshipModel
from .entity_extractor import EntityExtractor
from .neo4j_client import Neo4jClient
from .utils import setup_logger

logger = setup_logger(__name__)


def ingest_chunks(
    chunks: Iterable[Dict],
    extractor: EntityExtractor,
    neo4j_client: Neo4jClient,
    ingestion_id: Optional[str] = None,
) -> Dict:
    """Ingest provided chunks into Neo4j using the extractor and client.

    Each chunk should be a dict with keys: 'text', optional 'doc_id', optional 'chunk_id'.

    Returns a report with totals, successes, failures and the ingestion_id.
    """
    if ingestion_id is None:
        ingestion_id = uuid.uuid4().hex

    total = 0
    success = 0
    failures: List[Dict] = []

    for c in chunks:
        total += 1
        text = c.get("text") or c.get("chunk")
        doc_id = c.get("doc_id")
        chunk_id = c.get("chunk_id")
        if not text:
            failures.append({"reason": "missing_text", "chunk": c})
            continue
        try:
            extraction: ExtractionResult = extractor.extract_from_chunk(text, doc_id=doc_id, chunk_id=chunk_id)
            # upsert nodes
            for n in extraction.nodes:
                try:
                    neo4j_client.upsert_node(n)
                except Exception:
                    logger.exception("Failed to upsert node: %s", n)
                    failures.append({"reason": "upsert_node_failed", "node": n.to_dict(), "chunk": {"doc_id": doc_id, "chunk_id": chunk_id}})
            # upsert relationships
            for r in extraction.relationships:
                try:
                    neo4j_client.upsert_relationship(r)
                except Exception:
                    logger.exception("Failed to upsert relationship: %s", r)
                    failures.append({"reason": "upsert_rel_failed", "rel": r.to_dict(), "chunk": {"doc_id": doc_id, "chunk_id": chunk_id}})
            # record ingestion metadata linking
            try:
                # attach minimal extra metadata
                neo4j_client.record_ingestion_metadata(ingestion_id=ingestion_id, doc_id=doc_id, chunk_id=chunk_id, extra={"nodes": len(extraction.nodes), "rels": len(extraction.relationships)})
            except Exception:
                logger.exception("Failed to record ingestion metadata for doc=%s chunk=%s", doc_id, chunk_id)
            success += 1
        except Exception:
            logger.exception("Extraction or ingestion failed for chunk doc=%s chunk=%s", doc_id, chunk_id)
            failures.append({"reason": "extraction_failed", "chunk": c})

    report = {
        "ingestion_id": ingestion_id,
        "total_chunks": total,
        "successful_chunks": success,
        "failures": failures,
    }
    return report


# convenience CLI-like function
def ingest_from_list(chunks: List[Dict], extractor: EntityExtractor, neo4j_client: Neo4jClient) -> Dict:
    return ingest_chunks(chunks, extractor, neo4j_client)

