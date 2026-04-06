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

import json
import logging
import re
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


def _build_prompt(chunk_text: str) -> str:
    """Render extraction prompt with chunk text."""
    template = ENTITY_EXTRACTION_PROMPT

    if "{text}" in template:
        return template.replace("{text}", chunk_text)
    if "{chunk}" in template:
        return template.replace("{chunk}", chunk_text)
    if "{chunk_text}" in template:
        return template.replace("{chunk_text}", chunk_text)

    return f"{template}\n\nText:\n{chunk_text}"


def extract_from_chunk(document: Document, client: Any | None = None) -> dict[str, Any] | None:
    """
    Extract entities/relations from a single chunk document.

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
        prompt = _build_prompt(chunk_text)
        response = llm.invoke(prompt)
        response_text = _response_to_text(response)
        try:
            extraction = _parse_extraction_json(response_text)
        except Exception as exc:
            logger.warning("Skipping chunk %s due to extraction error: %s", chunk_id, exc)
            logger.debug("Raw LLM response (first 500 chars): %s", response_text[:500])
            logger.debug("Chunk metadata=%s", metadata)
            return None

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


def extract_from_chunks(chunks: Sequence[Document]) -> list[dict[str, Any]]:
    """
    Extract entities/relations from chunked documents.

    Returns a list of extraction dictionaries paired with source metadata.
    """
    if not chunks:
        logger.warning("No chunks provided to extract_from_chunks")
        return []

    client = get_client(temperature=0)

    logger.info("Starting extraction for %s chunks using model=%s", len(chunks), MODEL)

    results: list[dict[str, Any]] = []
    skipped = 0

    for chunk in chunks:
        result = extract_from_chunk(document=chunk, client=client)
        if result is None:
            skipped += 1
            continue
        results.append(result)

    logger.info(
        "Finished extraction: input_chunks=%s extracted=%s skipped=%s",
        len(chunks),
        len(results),
        skipped,
    )

    return results
