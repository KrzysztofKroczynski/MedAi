"""Parameterised Cypher query runner for the MedGraph AI agent.

All templates use $entity / $secondary_entity Neo4j parameters — user-supplied
strings are NEVER string-interpolated into query text (prevents graph injection).
"""

from shared.neo4j_client import get_driver
from agent.state import QueryPlan, EvidenceItem

# All templates use $entity and optionally $secondary_entity as parameters.
# toLower() used for case-insensitive matching.
# LIMIT 50 — consistent with shared/prompts.py convention.

CYPHER_TEMPLATES = {

    "indication": """
        MATCH (d)-[r:INDICATED_FOR]->(i:Indication)
        WHERE toLower(d.name) CONTAINS toLower($entity)
          AND (d:Drug OR d:ActiveIngredient)
        WITH d.name AS drug, i.name AS indication,
             reduce(s = [], c IN collect(r.source_citations) | s + c) AS source_citations
        RETURN drug, indication, source_citations
        ORDER BY size(source_citations) DESC
        LIMIT 100
    """,

    "contraindication": """
        MATCH (d)-[r:CONTRAINDICATED_IN]->(c)
        WHERE toLower(d.name) CONTAINS toLower($entity)
          AND (d:Drug OR d:ActiveIngredient)
          AND (c:Contraindication OR c:PatientGroup)
        WITH d.name AS drug, c.name AS contraindication, labels(c) AS node_labels,
             reduce(s = [], x IN collect(r.source_citations) | s + x) AS source_citations
        RETURN drug, contraindication, node_labels, source_citations
        ORDER BY size(source_citations) DESC
        LIMIT 100
    """,

    "adverse_effect": """
        MATCH (d)-[r:WARNS_FOR]->(a:AdverseEffect)
        WHERE toLower(d.name) CONTAINS toLower($entity)
          AND (d:Drug OR d:ActiveIngredient)
        WITH d.name AS drug, a.name AS adverse_effect,
             reduce(s = [], c IN collect(r.source_citations) | s + c) AS source_citations
        RETURN drug, adverse_effect, source_citations
        ORDER BY size(source_citations) DESC
        LIMIT 150
    """,

    "dose": """
        MATCH (d)-[r:HAS_DOSE]->(dos:Dose)
        WHERE toLower(d.name) CONTAINS toLower($entity)
          AND (d:Drug OR d:ActiveIngredient)
        WITH d.name AS drug, dos.name AS dose_detail,
             reduce(s = [], c IN collect(r.source_citations) | s + c) AS source_citations
        RETURN drug, dose_detail, source_citations
        ORDER BY size(source_citations) DESC
        LIMIT 100
    """,

    "interaction": """
        MATCH (d1)-[r:INTERACTS_WITH]-(d2)
        WHERE toLower(d1.name) CONTAINS toLower($entity)
          AND (d1:Drug OR d1:ActiveIngredient)
          AND (d2:Drug OR d2:ActiveIngredient)
          AND ($secondary_entity = "" OR
               toLower(d2.name) CONTAINS toLower($secondary_entity))
        WITH d1.name AS drug1, d2.name AS drug2,
             reduce(s = [], c IN collect(r.source_citations) | s + c) AS source_citations,
             collect(r.doc_type)[0] AS doc_type
        RETURN drug1, drug2, source_citations, doc_type
        ORDER BY size(source_citations) DESC
        LIMIT 100
    """,

    "alternative": """
        MATCH (d1)-[r:ALTERNATIVE_FOR]-(d2)
        WHERE toLower(d1.name) CONTAINS toLower($entity)
          AND (d1:Drug OR d1:ActiveIngredient)
          AND (d2:Drug OR d2:ActiveIngredient)
        WITH d1.name AS drug, d2.name AS alternative,
             reduce(s = [], c IN collect(r.source_citations) | s + c) AS source_citations,
             collect(r.doc_type)[0] AS doc_type
        RETURN drug, alternative, source_citations, doc_type
        LIMIT 100
    """,

    "patient_group": """
        MATCH (d)-[r]->(pg:PatientGroup)
        WHERE toLower(d.name) CONTAINS toLower($entity)
          AND (d:Drug OR d:ActiveIngredient)
          AND type(r) IN ["CONTRAINDICATED_IN", "WARNS_FOR", "HAS_DOSE"]
        WITH d.name AS drug, pg.name AS patient_group, type(r) AS relation_type,
             reduce(s = [], c IN collect(r.source_citations) | s + c) AS source_citations
        RETURN drug, patient_group, relation_type, source_citations
        ORDER BY size(source_citations) DESC
        LIMIT 100
    """,

    "general": """
        MATCH (d)
        WHERE toLower(d.name) CONTAINS toLower($entity)
          AND (d:Drug OR d:ActiveIngredient)
        OPTIONAL MATCH (d)-[r1:INDICATED_FOR]->(i:Indication)
        OPTIONAL MATCH (d)-[r2:WARNS_FOR]->(a:AdverseEffect)
        OPTIONAL MATCH (d)-[r3:CONTRAINDICATED_IN]->(c)
        RETURN d.name AS drug,
               collect(DISTINCT i.name)[0..5] AS indications,
               collect(DISTINCT a.name)[0..5] AS adverse_effects,
               collect(DISTINCT c.name)[0..3] AS contraindications,
               collect(DISTINCT r1.source_citations)[0..3]
                 + collect(DISTINCT r2.source_citations)[0..3]
                 + collect(DISTINCT r3.source_citations)[0..3] AS citations
        LIMIT 10
    """
}


def run_cypher_query(item: QueryPlan) -> EvidenceItem:
    """Execute a parameterised Cypher query for the given QueryPlan item."""
    driver = get_driver()
    template = CYPHER_TEMPLATES.get(item["intent"], CYPHER_TEMPLATES["general"])
    params = {
        "entity": item["entity"],
        "secondary_entity": item.get("secondary_entity", "")
    }

    with driver.session() as session:
        result = session.run(template, params)
        records = [dict(r) for r in result]

    if not records:
        return EvidenceItem(
            query_id=item["query_id"],
            source_type="neo4j",
            content="",
            source_citations=[],
            node_names=[],
            sufficient=False
        )

    # Collect source_citations from relationship props; fall back to node props.
    all_citations = []
    for r in records:
        cits = r.get("source_citations") or []
        if isinstance(cits, list) and cits:
            all_citations.extend(cits)
        elif r.get("source_file") and r.get("page_number") is not None:
            all_citations.append(f"{r['source_file']}|{r['page_number']}")
    all_citations = list(dict.fromkeys(all_citations))  # deduplicate, preserve order

    # Collect node names for quote assembly
    node_name_keys = [
        "indication", "contraindication", "adverse_effect", "dose_detail",
        "patient_group", "alternative", "drug2"
    ]
    node_names = []
    for r in records:
        for k in node_name_keys:
            if r.get(k):
                node_names.append(str(r[k]))
    node_names = list(dict.fromkeys(node_names))

    return EvidenceItem(
        query_id=item["query_id"],
        source_type="neo4j",
        content=str(records),
        source_citations=all_citations,
        node_names=node_names,
        sufficient=False
    )
