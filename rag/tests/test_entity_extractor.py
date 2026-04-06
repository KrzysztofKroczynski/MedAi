import json
import pytest

from rag.entity_extractor import EntityExtractor
from rag.models import ExtractionResult, NodeModel, RelationshipModel, Citation


def mock_llm_returning_json(prompt: str) -> str:
    # simple deterministic JSON response
    resp = {
        "nodes": [
            {"type": "Drug", "text": "ibuprofen", "properties": {"name": "ibuprofen", "dose": "200mg"}},
            {"type": "Drug", "text": "warfarin", "properties": {"name": "warfarin"}},
        ],
        "relationships": [
            {"type": "INTERACTS_WITH", "source": "ibuprofen", "target": "warfarin", "properties": {"severity": "moderate"}}
        ],
        "citations": [
            {"source_id": "SRC1", "doc_id": "docA", "page": 3, "excerpt": "ibuprofen may increase bleeding risk when combined with warfarin"}
        ]
    }
    return json.dumps(resp)


def mock_llm_invalid(prompt: str) -> str:
    return "this is not json"


def test_extract_from_chunk_parses_structured_json():
    extractor = EntityExtractor(llm_callable=mock_llm_returning_json)
    result: ExtractionResult = extractor.extract_from_chunk("dummy text", doc_id="docA", chunk_id="c1")

    assert isinstance(result, ExtractionResult)
    assert len(result.nodes) == 2
    names = sorted([n.properties.get("name") for n in result.nodes])
    assert names == ["ibuprofen", "warfarin"]

    # relationships
    assert len(result.relationships) == 1
    rel = result.relationships[0]
    assert rel.rel_type == "INTERACTS_WITH"
    # ensure relationship connects the parsed node ids
    assert rel.start_id and rel.end_id

    # citations
    assert len(result.citations) == 1
    c = result.citations[0]
    assert c.source_id == "SRC1"
    assert c.doc_id == "docA"


def test_extract_from_chunk_handles_invalid_json():
    extractor = EntityExtractor(llm_callable=mock_llm_invalid)
    result = extractor.extract_from_chunk("dummy text")
    assert isinstance(result, ExtractionResult)
    assert len(result.nodes) == 0
    assert len(result.relationships) == 0
    assert len(result.citations) == 0

