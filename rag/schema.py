"""Canonical graph schema and normalization helpers for rag.

Responsibilities implemented here:
- Canonical node label set and relationship type set
- Aliases/normalization maps for labels and relationship types
- Validation helpers and mapping helpers for extracted entities
"""

from typing import Dict, Iterable, List, Optional

# Canonical node labels used in the knowledge graph
CANONICAL_NODE_LABELS = {
    "Drug",
    "Condition",
    "Symptom",
    "Dosage",
    "Interaction",
    "Document",
    "Entity",
}

# Common aliases mapped to canonical labels
_LABEL_ALIASES: Dict[str, str] = {
    "medication": "Drug",
    "med": "Drug",
    "drug": "Drug",
    "drug_name": "Drug",
    "disease": "Condition",
    "condition": "Condition",
    "symptom": "Symptom",
    "sign": "Symptom",
    "dose": "Dosage",
    "dosage": "Dosage",
    "interaction": "Interaction",
    "document": "Document",
    "text_chunk": "Document",
    "entity": "Entity",
}

# Canonical relationship types
CANONICAL_REL_TYPES = {
    "TREATS",
    "CAUSES",
    "INTERACTS_WITH",
    "HAS_SYMPTOM",
    "MENTIONS",
    "MENTIONED_IN",
}

_REL_ALIAS: Dict[str, str] = {
    "treats": "TREATS",
    "treat": "TREATS",
    "causes": "CAUSES",
    "interacts": "INTERACTS_WITH",
    "interacts_with": "INTERACTS_WITH",
    "interaction": "INTERACTS_WITH",
    "has_symptom": "HAS_SYMPTOM",
    "mentions": "MENTIONS",
    "mentioned_in": "MENTIONED_IN",
}


def normalize_label(raw: Optional[str]) -> Optional[str]:
    """Normalize a raw label/role to a canonical node label.

    Returns None if no mapping exists.
    """
    if not raw:
        return None
    key = raw.strip().lower()
    if key in _LABEL_ALIASES:
        return _LABEL_ALIASES[key]
    # try simple title-case match
    candidate = raw.strip().title()
    if candidate in CANONICAL_NODE_LABELS:
        return candidate
    return None


def normalize_rel_type(raw: Optional[str]) -> Optional[str]:
    """Normalize a raw relationship type to a canonical relationship type.

    Returns None if no mapping exists.
    """
    if not raw:
        return None
    key = raw.strip().lower()
    if key in _REL_ALIAS:
        return _REL_ALIAS[key]
    candidate = raw.strip().upper()
    if candidate in CANONICAL_REL_TYPES:
        return candidate
    return None


def validate_node_labels(labels: Iterable[str]) -> List[str]:
    """Return a list of validated canonical labels. Raises ValueError for empty/invalid input.

    The function tolerates alias labels and normalizes them.
    """
    normalized: List[str] = []
    for l in labels:
        nl = normalize_label(l)
        if not nl:
            raise ValueError(f"Unknown node label or alias: {l}")
        if nl not in normalized:
            normalized.append(nl)
    if not normalized:
        raise ValueError("At least one valid node label is required")
    return normalized


def map_extracted_entity_to_schema(entity: Dict) -> Dict:
    """Map an extracted entity dict (from LLM extractor) to a schema-aligned dict.

    Expected entity shape (flexible): {"type": "drug", "text": "ibuprofen", "properties": {...}}

    Returns a dict: {"labels": [...], "properties": {...}}
    """
    raw_type = entity.get("type") or entity.get("label") or entity.get("role")
    label = normalize_label(raw_type) or "Entity"
    props = dict(entity.get("properties") or {})
    # ensure a canonical 'name' property when text is provided
    if "text" in entity and "name" not in props:
        props["name"] = entity.get("text")
    # retain raw_text for provenance
    if "text" in entity:
        props.setdefault("raw_text", entity.get("text"))
    # include source metadata if present
    for k in ("doc_id", "chunk_id", "source_id"):
        if k in entity:
            props.setdefault(k, entity[k])
    return {"labels": [label], "properties": props}

