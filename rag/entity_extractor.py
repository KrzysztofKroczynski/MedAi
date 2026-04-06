"""Entity extractor wrapper that uses an LLM callable to extract structured entities/relationships from text chunks.

Design:
- EntityExtractor(llm_callable) where llm_callable(prompt: str) -> str (LLM response string)
- extract_from_chunk(chunk, doc_id=None, chunk_id=None) -> ExtractionResult
- Uses prompts.build_extraction_prompt and utils.safe_json_loads to parse LLM JSON
- Returns models.ExtractionResult with NodeModel/RelationshipModel/Citation instances

The implementation is intentionally adapter-friendly for tests: pass a mock llm callable that returns a JSON string.
"""

from typing import Any, Callable, Dict, List, Optional
import logging

from . import prompts, utils, schema
from .models import ExtractionResult, NodeModel, RelationshipModel, Citation

logger = logging.getLogger(__name__)


class EntityExtractor:
    """Adapter around an LLM callable for extracting entities/relations from text chunks.

    The llm callable must accept a single string (prompt) and return the model's text output
    as a string. Tests should inject a mock callable to simulate LLM responses.
    """

    def __init__(self, llm_callable: Optional[Callable[[str], str]] = None):
        if llm_callable is None:
            raise ValueError("EntityExtractor requires an llm_callable. Provide a callable that accepts a prompt string and returns response string.")
        self.llm = llm_callable

    def extract_from_chunk(self, chunk: str, doc_id: Optional[str] = None, chunk_id: Optional[str] = None) -> ExtractionResult:
        prompt = prompts.build_extraction_prompt(chunk=chunk, doc_id=doc_id, chunk_id=chunk_id)
        logger.debug("Sending extraction prompt to LLM for doc=%s chunk=%s", doc_id, chunk_id)
        raw = self.llm(prompt)
        if raw is None:
            logger.debug("LLM returned None for extraction prompt")
            return ExtractionResult()
        parsed = utils.safe_json_loads(raw, default={})
        if not parsed:
            # Try to be permissive: the LLM may wrap the JSON; attempt to extract first {...}
            # fallback: return empty
            logger.debug("Failed to parse JSON from LLM output; returning empty ExtractionResult")
            return ExtractionResult()

        nodes_out: List[NodeModel] = []
        relationships_out: List[RelationshipModel] = []
        citations_out: List[Citation] = []

        # parse nodes
        for n in parsed.get("nodes", []):
            try:
                if isinstance(n, NodeModel):
                    nodes_out.append(n)
                    continue
                # expected shapes: {"type":..., "text":..., "properties":{}}
                # map to canonical schema labels/properties when possible
                mapped = schema.map_extracted_entity_to_schema(n)
                labels = mapped.get("labels", ["Entity"]) or ["Entity"]
                props = dict(mapped.get("properties", {}))
                # ensure canonical name from text/raw fields if still missing
                text = n.get("text") or n.get("name") or n.get("raw_text") or ""
                if text and "name" not in props:
                    props["name"] = text
                # include provenance/fallback keys
                for k in ("doc_id", "chunk_id", "source_id"):
                    if k in n:
                        props.setdefault(k, n[k])
                node_id = NodeModel.make_id(doc_id or "", chunk_id or "", props.get("name", text))
                nodes_out.append(NodeModel(id=node_id, labels=labels, properties=props))
            except Exception:
                logger.exception("Failed to parse node: %s", n)

        # build a map from surface/name -> id for relationship linking
        name_to_id = {p.properties.get("name"): p.id for p in nodes_out if p.properties.get("name")}

        # parse relationships
        for r in parsed.get("relationships", []):
            try:
                if isinstance(r, RelationshipModel):
                    relationships_out.append(r)
                    continue
                r_type = r.get("type") or r.get("rel_type") or r.get("relationship")
                r_type = schema.normalize_rel_type(r_type) or r_type
                source = r.get("source") or r.get("from") or r.get("source_name")
                target = r.get("target") or r.get("to") or r.get("target_name")
                props = dict(r.get("properties") or {})
                # resolve ids
                start_id = name_to_id.get(source) or NodeModel.make_id(doc_id or "", chunk_id or "", source or "")
                end_id = name_to_id.get(target) or NodeModel.make_id(doc_id or "", chunk_id or "", target or "")
                rel_id = RelationshipModel.make_id(start_id, end_id, r_type or "")
                relationships_out.append(RelationshipModel(id=rel_id, start_id=start_id, end_id=end_id, rel_type=r_type or "RELATED_TO", properties=props))
            except Exception:
                logger.exception("Failed to parse relationship: %s", r)

        # parse citations
        for c in parsed.get("citations", []):
            try:
                if isinstance(c, Citation):
                    citations_out.append(c)
                    continue
                source_id = c.get("source_id") or c.get("id")
                doc = c.get("doc_id")
                page = c.get("page")
                excerpt = c.get("excerpt") or c.get("text")
                if source_id:
                    citations_out.append(Citation(source_id=source_id, doc_id=doc, page=page, excerpt=excerpt))
            except Exception:
                logger.exception("Failed to parse citation: %s", c)

        metadata = parsed.get("metadata", {}) if isinstance(parsed, dict) else {}
        return ExtractionResult(nodes=nodes_out, relationships=relationships_out, citations=citations_out, metadata=metadata)


# simple helper factory to create an EntityExtractor from a langchain-like LLM client
def from_callable(llm_callable: Callable[[str], str]) -> EntityExtractor:
    return EntityExtractor(llm_callable=llm_callable)
