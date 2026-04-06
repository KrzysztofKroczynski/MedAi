# All LLM prompt templates used across the system.
#
# Should define:
#   ENTITY_EXTRACTION_PROMPT — instructs the configured LLM to extract entities and relations
#     from a medication text chunk and return structured JSON.
#     Entities: Drug, ActiveIngredient, Indication, Contraindication, AdverseEffect, Dose, PatientGroup.
#     Relations: CONTAINS, INDICATED_FOR, CONTRAINDICATED_IN, INTERACTS_WITH, ALTERNATIVE_FOR, HAS_DOSE, WARNS_FOR.
#
#   CYPHER_GENERATION_PROMPT — instructs the configured LLM to translate a user's natural language
#     question into a Neo4j Cypher READ query, given the graph schema.
#
#   QA_PROMPT — instructs the configured LLM to answer the user's question strictly from the
#     provided graph context (no invention). Must include source citations and a
#     medical disclaimer. If context is empty, must refuse to answer from model memory.

ENTITY_EXTRACTION_PROMPT = """
You are an information extraction system for medication leaflets and SmPC text.

Task:
- Extract entities and relations from the provided chunk.
- Return ONLY valid JSON (no markdown, no explanations).

Allowed entity types:
- Drug
- ActiveIngredient
- Indication
- Contraindication
- AdverseEffect
- Dose
- PatientGroup

Allowed relation types:
- CONTAINS
- INDICATED_FOR
- CONTRAINDICATED_IN
- INTERACTS_WITH
- ALTERNATIVE_FOR
- HAS_DOSE
- WARNS_FOR

Output JSON schema:
{
  "entities": [
    {"type": "Drug", "name": "Ibuprofen"}
  ],
  "relations": [
    {"from": "Ibuprofen", "rel": "INTERACTS_WITH", "to": "Warfarin"}
  ]
}

Rules:
- Use exact text spans when possible.
- Keep names concise and normalized.
- If nothing is found, return: {"entities": [], "relations": []}
- Ensure strict JSON validity.

Text chunk:
{text}
""".strip()
