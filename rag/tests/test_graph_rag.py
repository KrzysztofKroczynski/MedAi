import pytest

from rag.graph_rag import GraphRAG, from_callable as rag_from_callable
from rag.models import QueryResult, Citation


class DummyNeo4j:
    def __init__(self, nodes=None):
        # nodes is a list of dicts representing node properties
        self._nodes = nodes or []

    def run_query(self, cypher, params=None):
        # Return nodes wrapped as rows: {'node': node}
        # Simple behavior: ignore cypher and params and return the first few nodes
        rows = []
        for n in self._nodes:
            rows.append({"node": n})
        return rows


def test_answer_query_refusal_when_no_evidence():
    neo = DummyNeo4j(nodes=[])

    def llm(prompt: str) -> str:
        # Should not be called, but provide something
        return ""

    rag = GraphRAG(neo4j_client=neo, llm_callable=llm)
    res: QueryResult = rag.answer_query("Is this evidence present?", top_k=5, max_hops=1)

    assert isinstance(res, QueryResult)
    assert "cannot find sufficient evidence" in res.answer.lower()
    assert res.citations == []


def test_answer_query_returns_answer_and_citations():
    # create a node that includes source_id/doc_id/name/raw_text
    node = {"id": "n1", "source_id": "SRC1", "doc_id": "docA", "name": "ibuprofen", "raw_text": "ibuprofen may increase bleeding risk when combined with warfarin"}
    neo = DummyNeo4j(nodes=[node])

    def llm(prompt: str) -> str:
        # Simulate an LLM that obeys citation-first rule and references SRC1
        return "Ibuprofen can increase bleeding risk when combined with warfarin. [CITATION:SRC1]"

    rag = GraphRAG(neo4j_client=neo, llm_callable=llm)
    res = rag.answer_query("Can ibuprofen and warfarin be used together?", top_k=5, max_hops=1)

    assert isinstance(res, QueryResult)
    assert "bleeding" in res.answer.lower()
    assert len(res.citations) == 1
    assert res.citations[0].source_id == "SRC1"
    assert res.provenance and res.provenance[0]["snippet"] == node["raw_text"]

