import pytest

from rag.neo4j_client import Neo4jClient
from rag.models import NodeModel, RelationshipModel


def test_run_query_raises_when_driver_not_initialized():
    client = Neo4jClient(uri="bolt://none", user="u", password="p")
    # force driver to None to simulate environment without neo4j
    client._driver = None
    with pytest.raises(RuntimeError):
        client.run_query("MATCH (n) RETURN n")


def test_upsert_node_uses_run_query(monkeypatch):
    client = Neo4jClient(uri="bolt://none", user="u", password="p")

    called = {}

    def fake_run_query(cypher, params=None, db=None):
        called['cypher'] = cypher
        called['params'] = params
        return [{'node': {'id': params['id'], 'name': params['props'].get('name')}}]

    monkeypatch.setattr(client, 'run_query', fake_run_query)

    node = NodeModel(id='n1', labels=['Drug'], properties={'name': 'ibuprofen'})
    res = client.upsert_node(node)
    assert res['id'] == 'n1'
    assert res['name'] == 'ibuprofen'
    assert 'MERGE' in called['cypher']


def test_upsert_relationship_uses_run_query(monkeypatch):
    client = Neo4jClient(uri="bolt://none", user="u", password="p")

    called = {}

    def fake_run_query(cypher, params=None, db=None):
        called['cypher'] = cypher
        called['params'] = params
        return [{'rel': {'id': params['id'], 'start_id': params['start_id'], 'end_id': params['end_id']}}]

    monkeypatch.setattr(client, 'run_query', fake_run_query)

    rel = RelationshipModel(id='r1', start_id='n1', end_id='n2', rel_type='INTERACTS_WITH', properties={'severity': 'moderate'})
    res = client.upsert_relationship(rel)
    assert res['id'] == 'r1'
    assert res['start_id'] == 'n1'
    assert res['end_id'] == 'n2'
    assert 'MERGE' in called['cypher']

