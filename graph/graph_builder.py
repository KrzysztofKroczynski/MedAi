# Writes extracted entities and relations into Neo4j.
# Uses MERGE (not CREATE) to avoid duplicates across multiple PDF runs.
# For each entity: MERGE node by (type, name), set/update properties.
# For each relation: MERGE the relationship between the two nodes.
# Attaches source metadata (source_file, page_number) to each node and relationship.
# Should apply Neo4j schema constraints on startup (unique Drug.name, etc.).

"""Write extracted entities and relations into Neo4j.

Design goals:
- idempotent writes (MERGE, not CREATE)
- safe label/relation normalization
- attach source metadata to nodes and relationships
"""

from __future__ import annotations

import logging
import re
from typing import Any, Mapping, Sequence

from shared.neo4j_client import get_driver

logger = logging.getLogger(__name__)

_ALLOWED_LABELS = {
    "Drug",
    "ActiveIngredient",
    "Indication",
    "Contraindication",
    "AdverseEffect",
    "Dose",
    "PatientGroup",
    "Entity",
}

_LABEL_ALIASES = {
    "drug": "Drug",
    "activeingredient": "ActiveIngredient",
    "active_ingredient": "ActiveIngredient",
    "ingredient": "ActiveIngredient",
    "indication": "Indication",
    "contraindication": "Contraindication",
    "adverseeffect": "AdverseEffect",
    "sideeffect": "AdverseEffect",
    "dose": "Dose",
    "dosage": "Dose",
    "patientgroup": "PatientGroup",
    "group": "PatientGroup",
    "entity": "Entity",
}


def _normalize_label(raw_label: Any) -> str:
    if not isinstance(raw_label, str) or not raw_label.strip():
        return "Entity"

    compact = re.sub(r"[^a-zA-Z0-9_]", "", raw_label).strip().lower()
    if not compact:
        return "Entity"

    resolved = _LABEL_ALIASES.get(compact)
    if resolved in _ALLOWED_LABELS:
        return resolved

    pascal = "".join(part.capitalize() for part in re.split(r"[^a-zA-Z0-9]+", raw_label) if part)
    if pascal in _ALLOWED_LABELS:
        return pascal

    return "Entity"


def _normalize_rel_type(raw_rel: Any) -> str:
    if not isinstance(raw_rel, str) or not raw_rel.strip():
        return "RELATED_TO"

    rel = re.sub(r"[^A-Za-z0-9]+", "_", raw_rel.strip()).upper().strip("_")
    if not rel:
        return "RELATED_TO"
    if rel[0].isdigit():
        rel = f"REL_{rel}"
    return rel


def _normalize_name(raw_name: Any, label: str = "") -> str | None:
    if not isinstance(raw_name, str):
        return None
    name = raw_name.strip()
    if not name:
        return None
    # For Drug and ActiveIngredient: strip trailing dosage/formulation noise
    # e.g. "Ibuprofen 400mg Tablets" → "Ibuprofen", "Amoxicillin 500 mg capsules" → "Amoxicillin"
    if label in ("Drug", "ActiveIngredient"):
        name = re.sub(
            r"\s+\d[\d.,]*\s*(mg|mcg|g|ml|iu|mmol|%|unit).*$",
            "",
            name,
            flags=re.IGNORECASE,
        ).strip()
    # Title-case so "ibuprofen", "IBUPROFEN", "Ibuprofen" all merge to "Ibuprofen"
    return name.title() if name else None


def _upsert_node(session: Any, label: str, name: str, metadata: Mapping[str, Any]) -> None:
    cypher = f"""
    MERGE (n:{label} {{name: $name}})
    ON CREATE SET n.created_at = datetime()
    SET n.updated_at = datetime(),
        n.last_source_file = $source_file,
        n.last_page_number = $page_number,
        n.last_doc_type = $doc_type
    """
    session.run(
        cypher,
        name=name,
        source_file=metadata.get("source_file"),
        page_number=metadata.get("page_number"),
        doc_type=metadata.get("doc_type"),
    )


def _upsert_relation(
    session: Any,
    from_name: str,
    from_label: str,
    rel_type: str,
    to_name: str,
    to_label: str,
    metadata: Mapping[str, Any],
) -> None:
    cypher = f"""
    MATCH (a {{name: $from_name}})
    WHERE $from_label IN labels(a)
    MATCH (b {{name: $to_name}})
    WHERE $to_label IN labels(b)
    MERGE (a)-[r:{rel_type}]->(b)
    ON CREATE SET r.created_at = datetime()
    SET r.updated_at = datetime(),
        r.last_source_file = $source_file,
        r.last_page_number = $page_number,
        r.last_doc_type = $doc_type
    """
    session.run(
        cypher,
        from_name=from_name,
        from_label=from_label,
        to_name=to_name,
        to_label=to_label,
        source_file=metadata.get("source_file"),
        page_number=metadata.get("page_number"),
        doc_type=metadata.get("doc_type"),
    )


def write_extraction(extraction: Mapping[str, Any]) -> dict[str, int]:
    """Write a single extraction result into Neo4j."""
    entities = extraction.get("entities", []) or []
    relations = extraction.get("relations", []) or []
    metadata = extraction.get("metadata", {}) or {}

    if not isinstance(entities, list):
        entities = []
    if not isinstance(relations, list):
        relations = []
    if not isinstance(metadata, dict):
        metadata = {}

    label_by_name: dict[str, str] = {}
    node_writes = 0
    relation_writes = 0

    driver = get_driver()
    with driver.session() as session:
        for entity in entities:
            if not isinstance(entity, Mapping):
                continue
            label = _normalize_label(entity.get("type"))
            name = _normalize_name(entity.get("name"), label=label)
            if not name:
                continue

            _upsert_node(session, label=label, name=name, metadata=metadata)
            label_by_name[name] = label
            node_writes += 1

        for relation in relations:
            if not isinstance(relation, Mapping):
                continue

            from_name = _normalize_name(relation.get("from"))
            to_name = _normalize_name(relation.get("to"))
            if not from_name or not to_name:
                continue

            from_label = label_by_name.get(from_name, "Entity")
            to_label = label_by_name.get(to_name, "Entity")
            rel_type = _normalize_rel_type(relation.get("rel"))

            # Ensure endpoints exist, even when relation references entities
            # that were not extracted in the entities list.
            _upsert_node(session, label=from_label, name=from_name, metadata=metadata)
            _upsert_node(session, label=to_label, name=to_name, metadata=metadata)
            _upsert_relation(
                session,
                from_name=from_name,
                from_label=from_label,
                rel_type=rel_type,
                to_name=to_name,
                to_label=to_label,
                metadata=metadata,
            )
            relation_writes += 1

    return {"nodes": node_writes, "relations": relation_writes}


def write_extractions(extractions: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """Write many extraction records into Neo4j and return aggregate stats."""
    totals = {"records": 0, "nodes": 0, "relations": 0, "failed": 0}

    for extraction in extractions:
        if not isinstance(extraction, Mapping):
            totals["failed"] += 1
            continue

        try:
            stats = write_extraction(extraction)
            totals["records"] += 1
            totals["nodes"] += stats["nodes"]
            totals["relations"] += stats["relations"]
        except Exception:
            totals["failed"] += 1
            logger.exception("Failed to write one extraction record to Neo4j")

    logger.info(
        "Graph write finished: records=%s nodes=%s relations=%s failed=%s",
        totals["records"],
        totals["nodes"],
        totals["relations"],
        totals["failed"],
    )
    return totals