# Entity and relation extractor for medication text chunks.
# Calls the LLM using ENTITY_EXTRACTION_PROMPT from shared/prompts.py.
# Gets the client and model from shared/llm_client.py (MODEL).
# For each chunk, sends the text to the LLM and parses the returned JSON.
# Expected JSON structure:
#   {
#     "entities": [{"type": "Drug", "name": "Ibuprofen"}, ...],
#     "relations": [{"from": "Ibuprofen", "rel": "INTERACTS_WITH", "to": "Warfarin"}, ...]
#   }
# Should handle LLM errors and malformed JSON gracefully (log and skip the chunk).
# Returns a list of extraction result dicts, each paired with the chunk's source metadata.
"""Entity/relation extraction for medication text chunks."""

from __future__ import annotations

import os
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Sequence

from langchain_core.documents import Document

import shared.prompts as prompts
from shared.llm_client import MODEL, get_client

logger = logging.getLogger(__name__)

ENTITY_EXTRACTION_PROMPT = getattr(
    prompts,
    "ENTITY_EXTRACTION_PROMPT",
    (
        "Extract medication-related entities and relations from the text below. "
        "Return strictly valid JSON with this schema: "
        "{\"entities\":[{\"type\":\"...\",\"name\":\"...\"}],"
        "\"relations\":[{\"from\":\"...\",\"rel\":\"...\",\"to\":\"...\"}]}. "
        "Do not include markdown.\n\n"
        "Text:\n{text}"
    ),
)

# Maps section_type values (from section_splitter) to a concise hint injected
# into the extraction prompt to guide the LLM's entity type assignment.
_SECTION_HINTS: dict[str, str] = {
    "indication":       "This text is from the INDICATIONS section. Focus on Indication entities and INDICATED_FOR relations.",
    "contraindication": "This text is from the CONTRAINDICATIONS section. Focus on Contraindication and PatientGroup entities and CONTRAINDICATED_IN relations.",
    "warning":          "This text is from the WARNINGS/PRECAUTIONS section. Focus on PatientGroup and AdverseEffect entities and WARNS_FOR/CONTRAINDICATED_IN relations.",
    "adverse_effect":   "This text is from the ADVERSE REACTIONS/SIDE EFFECTS section. Focus on AdverseEffect entities and WARNS_FOR relations.",
    "dose":             "This text is from the DOSAGE/ADMINISTRATION section. Focus on Dose and PatientGroup entities and HAS_DOSE relations.",
    "interaction":      "This text is from the DRUG INTERACTIONS section. Focus on Drug and ActiveIngredient entities and INTERACTS_WITH relations.",
    "patient_group":    "This text is from the SPECIAL POPULATIONS section. Focus on PatientGroup entities and WARNS_FOR/CONTRAINDICATED_IN/HAS_DOSE relations.",
    "storage":          "This text is from the STORAGE/INACTIVE INGREDIENTS section. Minimal clinical entities expected — extract only if clearly present.",
    "unknown":          "",
}


def _response_to_text(response: Any) -> str:
    """Normalize LLM response objects to plain text."""
    content = getattr(response, "content", response)

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                maybe_text = item.get("text") or item.get("content")
                if isinstance(maybe_text, str):
                    parts.append(maybe_text)
        return "\n".join(parts)

    return str(content)


def _extract_json_candidate(raw_text: str) -> str:
    """Extract JSON payload from LLM text, including fenced JSON blocks."""
    text = (raw_text or "").strip()
    if not text:
        return ""

    fenced_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text, flags=re.IGNORECASE)
    if fenced_match:
        return fenced_match.group(1).strip()

    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        return text[first_brace : last_brace + 1].strip()

    return text


def _parse_extraction_json(raw_text: str) -> dict[str, list[dict[str, str]]]:
    """Parse and normalize extraction JSON output."""
    candidate = _extract_json_candidate(raw_text)
    parsed = json.loads(candidate)

    if not isinstance(parsed, dict):
        raise ValueError("Extraction response must be a JSON object.")

    raw_entities = parsed.get("entities", [])
    raw_relations = parsed.get("relations", [])

    if raw_entities is None:
        raw_entities = []
    if raw_relations is None:
        raw_relations = []

    if not isinstance(raw_entities, list) or not isinstance(raw_relations, list):
        raise ValueError("'entities' and 'relations' must be JSON arrays.")

    entities: list[dict[str, str]] = []
    for entity in raw_entities:
        if not isinstance(entity, dict):
            continue

        entity_type = entity.get("type")
        entity_name = entity.get("name")
        if not isinstance(entity_type, str) or not entity_type.strip():
            continue
        if not isinstance(entity_name, str) or not entity_name.strip():
            continue

        entities.append(
            {
                "type": entity_type.strip(),
                "name": entity_name.strip(),
            }
        )

    relations: list[dict[str, str]] = []
    for relation in raw_relations:
        if not isinstance(relation, dict):
            continue

        rel_from = relation.get("from")
        rel_type = relation.get("rel")
        rel_to = relation.get("to")

        if not isinstance(rel_from, str) or not rel_from.strip():
            continue
        if not isinstance(rel_type, str) or not rel_type.strip():
            continue
        if not isinstance(rel_to, str) or not rel_to.strip():
            continue

        relations.append(
            {
                "from": rel_from.strip(),
                "rel": rel_type.strip(),
                "to": rel_to.strip(),
            }
        )

    return {
        "entities": entities,
        "relations": relations,
    }


# ---------------------------------------------------------------------------
# Relation endpoint validation
# ---------------------------------------------------------------------------

# Maps relation type → (allowed from-labels, allowed to-labels)
_RELATION_RULES: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    "CONTAINS":           (frozenset({"Drug", "ActiveIngredient"}), frozenset({"ActiveIngredient"})),
    "INDICATED_FOR":      (frozenset({"Drug", "ActiveIngredient"}), frozenset({"Indication"})),
    "CONTRAINDICATED_IN": (frozenset({"Drug", "ActiveIngredient"}), frozenset({"Contraindication", "PatientGroup"})),
    "INTERACTS_WITH":     (frozenset({"Drug", "ActiveIngredient"}), frozenset({"Drug", "ActiveIngredient"})),
    "ALTERNATIVE_FOR":    (frozenset({"Drug", "ActiveIngredient"}), frozenset({"Drug", "ActiveIngredient"})),
    "HAS_DOSE":           (frozenset({"Drug", "ActiveIngredient"}), frozenset({"Dose"})),
    "WARNS_FOR":          (frozenset({"Drug", "ActiveIngredient"}), frozenset({"AdverseEffect", "PatientGroup"})),
}


def _entity_type_map(entities: list[dict[str, str]]) -> dict[str, str]:
    """Return {name: type} for quick lookup."""
    return {e["name"]: e["type"] for e in entities if "name" in e and "type" in e}


def _validate_relations(
    relations: list[dict[str, str]],
    entity_map: dict[str, str],
) -> tuple[list[dict[str, str]], list[tuple[dict[str, str], str]]]:
    """Split relations into (valid, invalid).

    invalid entries are (relation_dict, reason_string) tuples.

    Type checking is only applied when an endpoint is present in entity_map.
    Absent endpoints are passed through — they may have been declared in a
    different chunk of the same document and will be resolved by graph_builder
    via the global label map.
    """
    valid: list[dict[str, str]] = []
    invalid: list[tuple[dict[str, str], str]] = []

    for rel in relations:
        rel_type = rel.get("rel", "")
        from_name = rel.get("from", "")
        to_name = rel.get("to", "")

        if rel_type not in _RELATION_RULES:
            invalid.append((rel, f"unknown relation type '{rel_type}'"))
            continue

        allowed_from, allowed_to = _RELATION_RULES[rel_type]

        from_type = entity_map.get(from_name)
        to_type = entity_map.get(to_name)

        if from_type is not None and from_type not in allowed_from:
            invalid.append((rel, f"'from' type '{from_type}' not allowed for {rel_type} (allowed: {sorted(allowed_from)})"))
            continue
        if to_type is not None and to_type not in allowed_to:
            invalid.append((rel, f"'to' type '{to_type}' not allowed for {rel_type} (allowed: {sorted(allowed_to)})"))
            continue

        valid.append(rel)

    return valid, invalid


def _build_correction_prompt(
    original_prompt: str,
    entities: list[dict[str, str]],
    valid_relations: list[dict[str, str]],
    invalid_relations: list[tuple[dict[str, str], str]],
) -> str:
    """Build a targeted correction prompt for schema-violating relations."""
    lines = [
        original_prompt,
        "",
        "---",
        "Your previous response contained relations that violate the schema:",
        "",
    ]
    for rel, reason in invalid_relations:
        lines.append(f"  - {json.dumps(rel)}")
        lines.append(f"    ERROR: {reason}")

    lines += [
        "",
        "The following relations were VALID and must be kept unchanged:",
        json.dumps(valid_relations, indent=2),
        "",
        "Fix ONLY the invalid relations above (correct the entity types or remove them if unfixable).",
        "Return the COMPLETE corrected JSON including all valid relations and your fixes.",
        "Return ONLY valid JSON. No markdown, no explanation.",
    ]
    return "\n".join(lines)


def _build_prompt(chunk_text: str, section_type: str = "unknown") -> str:
    """Render extraction prompt with chunk text and optional section hint."""
    template = ENTITY_EXTRACTION_PROMPT
    hint = _SECTION_HINTS.get(section_type, "")

    if "{text}" in template:
        prompt = template.replace("{text}", chunk_text)
    elif "{chunk}" in template:
        prompt = template.replace("{chunk}", chunk_text)
    elif "{chunk_text}" in template:
        prompt = template.replace("{chunk_text}", chunk_text)
    else:
        prompt = f"{template}\n\nText:\n{chunk_text}"

    if "{section_hint}" in prompt:
        prompt = prompt.replace("{section_hint}", hint)

    return prompt


def _split_text(text: str) -> tuple[str, str]:
    """Split text near the midpoint at a natural paragraph or sentence boundary."""
    mid = len(text) // 2
    # Prefer splitting at a double newline closest to midpoint
    for search_fn, sep in [
        (lambda t, m: t.rfind("\n\n", 0, m), "\n\n"),
        (lambda t, m: t.rfind("\n", 0, m), "\n"),
        (lambda t, m: t.rfind(". ", 0, m), ". "),
    ]:
        pos = search_fn(text, mid)
        if pos != -1:
            split_at = pos + len(sep)
            return text[:split_at].strip(), text[split_at:].strip()
    # Hard split at midpoint
    return text[:mid].strip(), text[mid:].strip()


def _merge_extractions(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Merge two extraction dicts, deduplicating entities and relations."""
    seen_entities: set[tuple[str, str]] = set()
    entities: list[dict[str, str]] = []
    for e in a["entities"] + b["entities"]:
        key = (e.get("type", ""), e.get("name", ""))
        if key not in seen_entities:
            seen_entities.add(key)
            entities.append(e)

    seen_relations: set[tuple[str, str, str]] = set()
    relations: list[dict[str, str]] = []
    for r in a["relations"] + b["relations"]:
        key = (r.get("from", ""), r.get("rel", ""), r.get("to", ""))
        if key not in seen_relations:
            seen_relations.add(key)
            relations.append(r)

    return {"entities": entities, "relations": relations}


def _is_truncated(response: Any) -> bool:
    """Return True if the LLM response was cut off due to token limit."""
    metadata = getattr(response, "response_metadata", {}) or {}
    return metadata.get("finish_reason") == "length"


def extract_from_chunk(
    document: Document,
    client: Any | None = None,
    _depth: int = 0,
) -> dict[str, Any] | None:
    """
    Extract entities/relations from a single chunk document.

    If the LLM truncates the response due to token limits, the chunk is split
    in half and each half is extracted separately (capped at one level of
    recursion via _depth).

    Returns None if LLM call or JSON parsing fails.
    """
    chunk_text = (document.page_content or "").strip()
    if not chunk_text:
        logger.debug("Skipping empty chunk")
        return None

    metadata = dict(document.metadata or {})
    chunk_id = metadata.get("chunk_id", "unknown")

    try:
        llm = client or get_client(temperature=0)
        section_type = metadata.get("section_type", "unknown")
        prompt = _build_prompt(chunk_text, section_type=section_type)
        response = llm.invoke(prompt)

        # --- Truncation detection: split and re-extract rather than retry ---
        if _is_truncated(response) and _depth == 0:
            logger.warning(
                "Chunk %s truncated by token limit — splitting in half and re-extracting",
                chunk_id,
            )
            first_text, second_text = _split_text(chunk_text)
            results = []
            for part_text in (first_text, second_text):
                if not part_text:
                    continue
                part_doc = Document(page_content=part_text, metadata=metadata)
                part_result = extract_from_chunk(part_doc, client=llm, _depth=1)
                if part_result:
                    results.append(part_result)

            if not results:
                logger.warning("Chunk %s: both halves failed after split", chunk_id)
                return None

            merged = results[0]
            for r in results[1:]:
                merged_extraction = _merge_extractions(
                    {"entities": merged["entities"], "relations": merged["relations"]},
                    {"entities": r["entities"], "relations": r["relations"]},
                )
                merged = {**merged, **merged_extraction}

            logger.info(
                "Chunk %s split extraction succeeded: entities=%d relations=%d",
                chunk_id, len(merged["entities"]), len(merged["relations"]),
            )
            return {
                "text": chunk_text,
                "metadata": metadata,
                "entities": merged["entities"],
                "relations": merged["relations"],
                "model": MODEL,
            }

        response_text = _response_to_text(response)
        try:
            extraction = _parse_extraction_json(response_text)
        except Exception as exc:
            logger.warning("Chunk %s returned invalid JSON, retrying with error feedback: %s", chunk_id, exc)
            retry_prompt = (
                f"{prompt}\n\n"
                f"Your previous response was not valid JSON. Error: {exc}\n"
                f"Previous response: {response_text[:500]}\n\n"
                f"Return ONLY valid JSON matching the schema. No markdown, no explanation."
            )
            try:
                retry_response = llm.invoke(retry_prompt)
                retry_text = _response_to_text(retry_response)
                extraction = _parse_extraction_json(retry_text)
                logger.info("Chunk %s retry succeeded", chunk_id)
            except Exception as retry_exc:
                logger.warning("Skipping chunk %s after retry failed: %s", chunk_id, retry_exc)
                logger.debug("Raw LLM response (first 500 chars): %s", response_text[:500])
                logger.debug("Chunk metadata=%s", metadata)
                return None

        # --- Relation endpoint validation + correction retry ---
        entity_map = _entity_type_map(extraction["entities"])
        valid_rels, invalid_rels = _validate_relations(extraction["relations"], entity_map)

        if invalid_rels:
            logger.warning(
                "Chunk %s has %d invalid relation(s), retrying with correction prompt",
                chunk_id, len(invalid_rels),
            )
            for _, reason in invalid_rels:
                logger.debug("  Invalid relation: %s", reason)

            correction_prompt = _build_correction_prompt(
                prompt, extraction["entities"], valid_rels, invalid_rels
            )
            try:
                correction_response = llm.invoke(correction_prompt)
                correction_text = _response_to_text(correction_response)
                corrected = _parse_extraction_json(correction_text)
                corrected_entity_map = _entity_type_map(corrected["entities"])
                corrected_valid, corrected_invalid = _validate_relations(
                    corrected["relations"], corrected_entity_map
                )
                if corrected_invalid:
                    logger.warning(
                        "Chunk %s correction still has %d invalid relation(s) — dropping them",
                        chunk_id, len(corrected_invalid),
                    )
                extraction = {
                    "entities": corrected["entities"],
                    "relations": corrected_valid,
                }
                logger.info("Chunk %s correction retry succeeded", chunk_id)
            except Exception as corr_exc:
                logger.warning(
                    "Chunk %s correction retry failed (%s) — keeping %d valid relation(s)",
                    chunk_id, corr_exc, len(valid_rels),
                )
                extraction = {
                    "entities": extraction["entities"],
                    "relations": valid_rels,
                }

        return {
            "text": chunk_text,
            "metadata": metadata,
            "entities": extraction["entities"],
            "relations": extraction["relations"],
            "model": MODEL,
        }
    except Exception as exc:
        logger.warning("Skipping chunk %s due to LLM invocation error: %s", chunk_id, exc)
        logger.debug("Chunk metadata=%s", metadata)
        return None


def _resolve_max_workers(total_chunks: int) -> int:
    """Resolve a safe worker count for parallel extraction."""
    default_workers = min(8, total_chunks)
    raw_value = os.getenv("EXTRACTION_MAX_WORKERS")

    if not raw_value:
        return max(1, default_workers)

    try:
        configured = int(raw_value)
        if configured < 1:
            raise ValueError("must be >= 1")
    except Exception:
        logger.warning(
            "Invalid EXTRACTION_MAX_WORKERS=%r. Falling back to default=%s.",
            raw_value,
            default_workers,
        )
        return max(1, default_workers)

    return min(total_chunks, configured)


def extract_from_chunks(chunks: Sequence[Document]) -> list[dict[str, Any]]:
    """
    Extract entities/relations from chunked documents.

    Returns a list of extraction dictionaries paired with source metadata.
    """
    if not chunks:
        logger.warning("No chunks provided to extract_from_chunks")
        return []

    workers = _resolve_max_workers(len(chunks))

    logger.info(
        "Starting extraction for %s chunks using model=%s workers=%s",
        len(chunks),
        MODEL,
        workers,
    )

    results_by_index: dict[int, dict[str, Any]] = {}
    skipped = 0

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="extractor") as executor:
        futures = {
            executor.submit(extract_from_chunk, document=chunk, client=None): index
            for index, chunk in enumerate(chunks)
        }

        for future in as_completed(futures):
            index = futures[future]
            chunk = chunks[index]
            metadata = dict(chunk.metadata or {})
            chunk_id = metadata.get("chunk_id", "unknown")

            try:
                result = future.result()
            except Exception as exc:
                logger.warning("Skipping chunk %s due to worker error: %s", chunk_id, exc)
                logger.debug("Chunk metadata=%s", metadata)
                skipped += 1
                continue

            if result is None:
                skipped += 1
                continue

            results_by_index[index] = result

    results = [results_by_index[i] for i in sorted(results_by_index)]

    logger.info(
        "Finished extraction: input_chunks=%s extracted=%s skipped=%s workers=%s",
        len(chunks),
        len(results),
        skipped,
        workers,
    )

    return results
