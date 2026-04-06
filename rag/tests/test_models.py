import json

from rag.models import Citation, NodeModel, RelationshipModel, ExtractionResult, QueryResult


def test_citation_serialization():
    c = Citation(source_id="S1", doc_id="docA", page=2, excerpt="some excerpt")
    d = c.to_dict()
    assert d["source_id"] == "S1"
    c2 = Citation.from_dict(d)
    assert c2.source_id == c.source_id
    assert c2.doc_id == c.doc_id


def test_node_and_relationship_serialization_and_ids():
    nid = NodeModel.make_id("docA", "c1", "ibuprofen")
    node = NodeModel(id=nid, labels=["Drug"], properties={"name": "ibuprofen"})
    d = node.to_dict()
    assert d["id"] == nid
    node2 = NodeModel.from_dict(d)
    assert node2.id == node.id
    assert node2.properties["name"] == "ibuprofen"

    rid = RelationshipModel.make_id(node.id, "n2", "INTERACTS_WITH")
    rel = RelationshipModel(id=rid, start_id=node.id, end_id="n2", rel_type="INTERACTS_WITH", properties={"severity": "low"})
    rd = rel.to_dict()
    rel2 = RelationshipModel.from_dict(rd)
    assert rel2.id == rid
    assert rel2.start_id == node.id


def test_extraction_and_query_result_helpers():
    er = ExtractionResult(nodes=[], relationships=[], citations=[], metadata={"foo": "bar"})
    ed = er.to_dict()
    assert ed["metadata"]["foo"] == "bar"
    er2 = ExtractionResult.from_dict(ed)
    assert er2.metadata["foo"] == "bar"

    qr = QueryResult.empty_refusal()
    assert "cannot find sufficient evidence" in qr.answer.lower()
    qd = qr.to_dict()
    assert qd["confidence"] == 0.0 or qd["confidence"] == 0

