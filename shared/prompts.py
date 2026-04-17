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
- Drug          — a medication product or substance used therapeutically, including substance classes
                  (e.g. "Ibuprofen", "Warfarin", "Alcohol", "Opioids", "Benzodiazepines", "NSAIDs")
- ActiveIngredient — the pharmacologically active chemical in a Drug (INN name)
- Indication    — a condition or symptom the drug treats (e.g. "pain", "hypertension")
- Contraindication — a condition making the drug unsafe (e.g. "severe hepatic impairment")
- AdverseEffect — an unwanted effect the drug may cause (e.g. "nausea", "liver damage")
- Dose          — a specific dosing instruction SCOPED to its drug, format: "{DrugName}:{dose detail}"
                  (e.g. "Ibuprofen:400mg every 6-8 hours", "Ibuprofen:max 1200mg/day")
- PatientGroup  — a patient population with special considerations
                  (e.g. "elderly patients", "children under 12", "patients with renal impairment",
                  "pregnant women", "breastfeeding women")

Allowed relation types and their ONLY valid endpoint types:
- CONTAINS           : Drug → ActiveIngredient
- INDICATED_FOR      : Drug or ActiveIngredient → Indication
- CONTRAINDICATED_IN : Drug or ActiveIngredient → Contraindication OR PatientGroup
- INTERACTS_WITH     : Drug or ActiveIngredient → Drug or ActiveIngredient
- ALTERNATIVE_FOR    : Drug or ActiveIngredient → Drug or ActiveIngredient
                       (use ONLY for therapeutic substitutes with same/similar effect,
                        NEVER for treatments of a condition)
- HAS_DOSE           : Drug or ActiveIngredient → Dose
- WARNS_FOR          : Drug or ActiveIngredient → AdverseEffect OR PatientGroup
                       (use for warnings specific to a patient population,
                        e.g. Drug WARNS_FOR PatientGroup when special caution applies)

Output JSON schema:
{
  "entities": [
    {"type": "Drug", "name": "Ibuprofen"},
    {"type": "PatientGroup", "name": "elderly patients"},
    {"type": "Dose", "name": "Ibuprofen:400mg every 6-8 hours"}
  ],
  "relations": [
    {"from": "Ibuprofen", "rel": "INTERACTS_WITH", "to": "Warfarin"},
    {"from": "Ibuprofen", "rel": "CONTRAINDICATED_IN", "to": "elderly patients"},
    {"from": "Ibuprofen", "rel": "WARNS_FOR", "to": "elderly patients"},
    {"from": "Ibuprofen", "rel": "HAS_DOSE", "to": "Ibuprofen:400mg every 6-8 hours"}
  ]
}

Naming rules — follow these exactly:
- Drug names: always use the INN (International Nonproprietary Name) generic name only.
  NEVER include brand names, dosage, formulation, or route in the Drug name.
  Correct: "Ibuprofen" — Wrong: "Advil", "Ibuprofen 400mg", "Ibuprofen Tablets"
- If a brand name appears (e.g. "Advil", "Nurofen"), map it to its INN generic name.
- Substance classes acting as drugs in interactions/warnings ARE Drug entities:
  Correct: Drug:"Alcohol", Drug:"Opioids", Drug:"NSAIDs", Drug:"Benzodiazepines"
- ActiveIngredient names: INN generic name only, same rules as Drug.
- Dose names MUST be prefixed with the drug name:
  Format: "{DrugName}:{dose detail}"
  Correct: "Ibuprofen:400mg every 6–8 hours", "Metformin:500mg twice daily"
  Wrong: "400mg", "twice daily", "500mg"
- PatientGroup names: descriptive phrase, lowercase.
  Correct: "elderly patients", "children under 12", "patients with renal impairment"
- All other entity names: concise, lowercase, no trailing punctuation.

Critical rules:
- ALWAYS create a relation linking PatientGroup to its drug when a warning or
  contraindication applies to that group. Never extract an isolated PatientGroup.
- ALWAYS create a relation linking Dose to its drug via HAS_DOSE.
  Never extract an isolated Dose.
- ALTERNATIVE_FOR = therapeutic substitute only (same/similar drug class or active ingredient).
  NEVER use ALTERNATIVE_FOR when the drug treats or reverses a condition/overdose.
- If nothing is found, return: {"entities": [], "relations": []}
- Ensure strict JSON validity.

Text chunk:
{text}
""".strip()
