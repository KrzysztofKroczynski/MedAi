"""Write extracted entities and relations into Neo4j.

Design goals:
- idempotent writes (MERGE, not CREATE)
- safe label/relation normalization
- attach source metadata to nodes and relationships
- batch UNWIND writes for performance (one session, ~14 queries total)
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
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

# These labels get their own MERGE key (label + name).
# Everything else merges under ClinicalConcept and gets the specific label added on top.
_ANCHOR_LABELS = {"Drug", "ActiveIngredient"}

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
    if label in ("Drug", "ActiveIngredient"):
        name = re.sub(
            r"\s+\d[\d.,]*\s*(mg|mcg|g|ml|iu|mmol|%|unit).*$",
            "",
            name,
            flags=re.IGNORECASE,
        ).strip()
    # Dose names must be "DrugName:dose detail".
    if label == "Dose":
        if ":" not in name:
            logger.warning("Dose entity missing drug prefix (expected 'DrugName:detail'): %r — dropping", name)
            return None
        prefix, _, detail = name.partition(":")
        if not prefix.strip():
            logger.warning("Dose entity has empty drug prefix: %r — dropping", name)
            return None
        return f"{prefix.strip().title()}:{detail.strip().lower()}"

    return name.title() if name else None


def _build_global_label_map(
    extractions: Sequence[Mapping[str, Any]],
    on_record: Any = None,
) -> dict[str, set[str]]:
    """Scan all extractions and build a name → set-of-labels map."""
    global_map: dict[str, set[str]] = {}
    for extraction in extractions:
        if not isinstance(extraction, Mapping):
            continue
        for entity in extraction.get("entities", []) or []:
            if not isinstance(entity, Mapping):
                continue
            label = _normalize_label(entity.get("type"))
            if label == "Entity":
                continue
            raw = entity.get("name")
            name = _normalize_name(raw, label=label)
            if name:
                global_map.setdefault(name, set()).add(label)
                # Also register the basic-normalized form as an alias so that
                # relation endpoints (which are normalized without a label) can
                # still resolve to the right label via this map.
                basic = _normalize_name(raw)
                if basic and basic != name:
                    global_map.setdefault(basic, set()).add(label)
        if on_record is not None:
            on_record()
    return global_map


def _resolve_labels(
    name: str,
    local_label_by_name: dict[str, str],
    global_label_map: dict[str, set[str]],
) -> list[str]:
    """Return the label(s) to use for a relation endpoint.

    Priority:
    1. Local chunk map (most specific).
    2. Global map. Drug wins over ActiveIngredient when both present.
    3. Fall back to Entity.
    """
    local = local_label_by_name.get(name)
    if local and local != "Entity":
        return [local]

    global_labels = global_label_map.get(name)
    if global_labels:
        if "Drug" in global_labels and "ActiveIngredient" in global_labels:
            resolved = global_labels - {"ActiveIngredient"}
            return sorted(resolved)
        return sorted(global_labels)

    return ["Entity"]


# ---------------------------------------------------------------------------
# Batch write helpers (UNWIND-based)
# ---------------------------------------------------------------------------

def _batch_upsert_anchor_nodes(session: Any, label: str, rows: list[dict]) -> None:
    """UNWIND upsert for Drug / ActiveIngredient nodes."""
    cypher = f"""
    UNWIND $rows AS row
    MERGE (n:{label} {{name: row.name}})
    ON CREATE SET n.created_at = datetime(),
                  n.source_file = row.source_file,
                  n.page_number = row.page_number,
                  n.doc_type    = row.doc_type
    ON MATCH SET  n.updated_at  = datetime()
    """
    session.run(cypher, rows=rows)


def _batch_upsert_concept_nodes(session: Any, label: str, rows: list[dict]) -> None:
    """UNWIND upsert for ClinicalConcept nodes (Indication, AdverseEffect, etc.)."""
    cypher = f"""
    UNWIND $rows AS row
    MERGE (n:ClinicalConcept {{name: row.name}})
    ON CREATE SET n.created_at = datetime(),
                  n.source_file = row.source_file,
                  n.page_number = row.page_number,
                  n.doc_type    = row.doc_type
    ON MATCH SET  n.updated_at  = datetime()
    SET n:{label}
    """
    session.run(cypher, rows=rows)


def _batch_upsert_relations(session: Any, rel_type: str, rows: list[dict]) -> None:
    """UNWIND upsert for relationships of a single type."""
    cypher = f"""
    UNWIND $rows AS row
    MATCH (a {{name: row.from_name}}) WHERE row.from_label IN labels(a)
    MATCH (b {{name: row.to_name}})   WHERE row.to_label   IN labels(b)
    MERGE (a)-[r:{rel_type}]->(b)
    ON CREATE SET r.created_at = datetime(),
                  r.doc_type   = row.doc_type,
                  r.source_citations = CASE
                    WHEN row.citation IS NOT NULL THEN [row.citation]
                    ELSE []
                  END
    ON MATCH SET  r.updated_at = datetime(),
                  r.source_citations = CASE
                    WHEN row.citation IS NULL
                      THEN coalesce(r.source_citations, [])
                    WHEN row.citation IN coalesce(r.source_citations, [])
                      THEN coalesce(r.source_citations, [])
                    ELSE coalesce(r.source_citations, []) + row.citation
                  END
    """
    session.run(cypher, rows=rows)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def write_extraction(
    extraction: Mapping[str, Any],
    global_label_map: dict[str, set[str]] | None = None,
) -> dict[str, int]:
    """Write a single extraction result into Neo4j (thin wrapper over write_extractions)."""
    return write_extractions([extraction], _prebuilt_global_map=global_label_map)


def write_extractions(
    extractions: Sequence[Mapping[str, Any]],
    _prebuilt_global_map: dict[str, set[str]] | None = None,
    on_label_map_record: Any = None,
    on_collect_record: Any = None,
) -> dict[str, int]:
    """Write many extraction records into Neo4j using batched UNWIND queries.

    Optional callbacks (each called with no arguments after each record):
      on_label_map_record — fired during the global label map pass
      on_collect_record   — fired during the data collection pass
    """
    totals = {"records": 0, "nodes": 0, "relations": 0, "failed": 0}

    global_label_map = _prebuilt_global_map if _prebuilt_global_map is not None \
        else _build_global_label_map(extractions, on_record=on_label_map_record)
    logger.info("Global label map built: %d unique names", len(global_label_map))

    # Accumulate rows per label / rel_type across all extractions.
    # Use sets to deduplicate nodes before sending to Neo4j.
    anchor_rows: dict[str, list[dict]] = defaultdict(list)   # label  -> rows
    concept_rows: dict[str, list[dict]] = defaultdict(list)  # label  -> rows
    rel_rows: dict[str, list[dict]] = defaultdict(list)       # rel_type -> rows

    seen_nodes: set[tuple[str, str]] = set()  # (label, name) already queued

    def _queue_node(label: str, name: str, meta: dict) -> None:
        key = (label, name)
        if key in seen_nodes:
            return
        seen_nodes.add(key)
        row = {
            "name": name,
            "source_file": meta.get("source_file"),
            "page_number": meta.get("page_number"),
            "doc_type": meta.get("doc_type"),
        }
        if label in _ANCHOR_LABELS:
            anchor_rows[label].append(row)
        else:
            concept_rows[label].append(row)

    for extraction in extractions:
        if not isinstance(extraction, Mapping):
            totals["failed"] += 1
            continue

        try:
            entities = extraction.get("entities", []) or []
            relations = extraction.get("relations", []) or []
            metadata = extraction.get("metadata", {}) or {}

            if not isinstance(entities, list):
                entities = []
            if not isinstance(relations, list):
                relations = []
            if not isinstance(metadata, dict):
                metadata = {}

            local_label_by_name: dict[str, str] = {}

            # --- entities ---
            for entity in entities:
                if not isinstance(entity, Mapping):
                    continue
                raw = entity.get("name")
                label = _normalize_label(entity.get("type"))
                name = _normalize_name(raw, label=label)
                if not name:
                    continue
                _queue_node(label, name, metadata)
                local_label_by_name[name] = label
                # Basic-normalized alias: relation endpoints are looked up by
                # basic-normalized name, so they must be able to find the label
                # even when the label-aware form differs (e.g. Dose names).
                basic = _normalize_name(raw)
                if basic and basic != name:
                    local_label_by_name.setdefault(basic, label)
                totals["nodes"] += 1

            # --- relations ---
            source_file = metadata.get("source_file") or ""
            page_number = metadata.get("page_number")
            citation = f"{source_file}|{page_number}" if source_file else None
            doc_type = metadata.get("doc_type")

            for relation in relations:
                if not isinstance(relation, Mapping):
                    continue

                raw_from = relation.get("from")
                raw_to = relation.get("to")
                # Basic-normalized names used only for label lookup.
                from_key = _normalize_name(raw_from)
                to_key = _normalize_name(raw_to)
                if not from_key or not to_key:
                    continue

                rel_type = _normalize_rel_type(relation.get("rel"))
                from_labels = _resolve_labels(from_key, local_label_by_name, global_label_map)
                to_labels = _resolve_labels(to_key, local_label_by_name, global_label_map)

                # Re-normalize with the resolved label so the DB name matches
                # exactly what was stored for the entity node (critical for
                # Dose names where label-aware and basic normalization differ).
                from_names = {
                    fl: (_normalize_name(raw_from, label=fl) or from_key)
                    for fl in from_labels
                }
                to_names = {
                    tl: (_normalize_name(raw_to, label=tl) or to_key)
                    for tl in to_labels
                }

                # Ensure endpoint nodes are queued under their canonical names.
                for fl, fn in from_names.items():
                    _queue_node(fl, fn, metadata)
                for tl, tn in to_names.items():
                    _queue_node(tl, tn, metadata)

                for fl in from_labels:
                    for tl in to_labels:
                        rel_rows[rel_type].append({
                            "from_name": from_names[fl],
                            "from_label": fl,
                            "to_name": to_names[tl],
                            "to_label": tl,
                            "citation": citation,
                            "doc_type": doc_type,
                        })
                        totals["relations"] += 1

            totals["records"] += 1
            if on_collect_record is not None:
                on_collect_record()

        except Exception:
            totals["failed"] += 1
            logger.exception("Failed to process extraction record")

    # --- single session, batch writes ---
    driver = get_driver()
    with driver.session() as session:
        for label, rows in anchor_rows.items():
            logger.debug("Batch upsert %s anchor nodes (%d rows)", label, len(rows))
            _batch_upsert_anchor_nodes(session, label, rows)

        for label, rows in concept_rows.items():
            logger.debug("Batch upsert %s concept nodes (%d rows)", label, len(rows))
            _batch_upsert_concept_nodes(session, label, rows)

        for rel_type, rows in rel_rows.items():
            logger.debug("Batch upsert %s relations (%d rows)", rel_type, len(rows))
            _batch_upsert_relations(session, rel_type, rows)

    logger.info(
        "Graph write finished: records=%s nodes=%s relations=%s failed=%s",
        totals["records"],
        totals["nodes"],
        totals["relations"],
        totals["failed"],
    )
    return totals
