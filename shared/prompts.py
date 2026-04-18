# All LLM prompt templates used across the system.
#
#   ENTITY_EXTRACTION_PROMPT — extracts entities and relations from a medication text chunk.
#     Placeholders: {text} (chunk content), {section_hint} (injected by extractor.py based
#     on the page's detected section type — indication, dose, adverse_effect, etc.).
#     Entities: Drug, ActiveIngredient, Indication, Contraindication, AdverseEffect, Dose, PatientGroup.
#     Relations: CONTAINS, INDICATED_FOR, CONTRAINDICATED_IN, INTERACTS_WITH, ALTERNATIVE_FOR, HAS_DOSE, WARNS_FOR.
#
#   CYPHER_GENERATION_PROMPT — translates a natural language question into a Neo4j Cypher READ query.
#     Reflects the multi-label schema: clinical concept nodes carry both ClinicalConcept (base)
#     and their specific label (e.g. Indication, AdverseEffect). Queries should match by specific label.
#     Placeholder: {question}.
#
#   QA_PROMPT — generates a grounded answer from graph context. Refuses to answer when context
#     is empty. Placeholders: {context}, {question}.

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

Naming rules — follow these exactly (IMPORTANT):
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

Section context (if provided, use it to guide entity type assignment):
{section_hint}

Text chunk:
{text}
""".strip()

CYPHER_GENERATION_PROMPT = """
You are a Neo4j Cypher expert for a pharmaceutical knowledge graph.

Graph schema
============
Node labels:
  Drug             — a medication product (e.g. "Ibuprofen", "Warfarin")
                     ANCHOR label: has its own unique constraint on name.
  ActiveIngredient — the pharmacologically active chemical in a Drug (INN name)
                     ANCHOR label: has its own unique constraint on name.
                     NOTE: when the same name appears as both Drug and ActiveIngredient
                     across documents, the Drug label takes precedence — that node will
                     only have the Drug label, not ActiveIngredient.
  ClinicalConcept  — BASE label shared by all clinical concept nodes below.
                     Do NOT query by :ClinicalConcept alone — always use the specific label.
  Indication       — (:ClinicalConcept) a condition the drug treats (e.g. "pain", "hypertension")
  Contraindication — (:ClinicalConcept) a condition making the drug unsafe
  AdverseEffect    — (:ClinicalConcept) an unwanted side-effect
  Dose             — (:ClinicalConcept) a dosing instruction; name format: "DrugName:dose detail"
                     where DrugName is title-cased and dose detail is lowercase
                     (e.g. "Ibuprofen:400mg every 6-8 hours", "Metformin:500mg twice daily")
  PatientGroup     — (:ClinicalConcept) a patient population (e.g. "elderly patients")

IMPORTANT — multi-label nodes:
  A single ClinicalConcept node can accumulate multiple specific labels if the same concept
  appears in different roles across documents (e.g. a node may be both :AdverseEffect
  and :Contraindication). Always match by the specific label.
  Example: MATCH (e:AdverseEffect) WHERE toLower(e.name) CONTAINS toLower('nausea')

Node properties: name, source_file, page_number (first-seen only — internal, do not cite)

Relationship properties:
  source_citations — list of strings "filename.pdf|page" for every PIL page that states this fact
  (e.g. ["ibuprofen_leaflet.pdf|5", "warfarin_smpc.pdf|12"])

Relationship types (direction):
  CONTAINS            Drug        → ActiveIngredient
  INDICATED_FOR       Drug/AI     → Indication
  CONTRAINDICATED_IN  Drug/AI     → Contraindication | PatientGroup
  INTERACTS_WITH      Drug/AI     → Drug | ActiveIngredient
  ALTERNATIVE_FOR     Drug/AI     → Drug | ActiveIngredient
  HAS_DOSE            Drug/AI     → Dose
  WARNS_FOR           Drug/AI     → AdverseEffect | PatientGroup

Rules
=====
1. Generate a single READ-only Cypher (MATCH + RETURN only — no CREATE, MERGE, SET, DELETE).
2. Use case-insensitive name matching: toLower(n.name) CONTAINS toLower('keyword').
3. Always RETURN human-readable columns — prefer aliases like drug_name, interaction, dose.
4. Always include citations in every RETURN using the traversed relationship:
       r.source_citations AS source_citations
   If multiple relationships are collected in the query use:
       collect(r.source_citations) AS source_citations
   Never cite node properties — relationship source_citations is the authoritative PIL source.
5. LIMIT 50.
6. Output ONLY the raw Cypher query — no markdown fences, no explanation.

Question: {question}
""".strip()

QA_PROMPT = """
You are a clinical pharmacology assistant. Answer the user's question using ONLY the
information provided in the Context section below.

Rules:
- Base your answer strictly on the context — do NOT use prior knowledge or training data.
- Synthesise the information into a clear, structured answer; do not copy rows verbatim.
- If the context is empty or does not contain enough information to answer, respond with:
  "The available medication documents do not contain sufficient information to answer this question.
   Please consult a doctor or pharmacist."
  Do NOT attempt to answer from your own training data.
- Do not invent drug names, doses, or interactions not present in the context.
- Be concise and medically accurate.
- At the end of your answer, list the source documents referenced, using the source_citations
  values from the context (format: filename | page). Label this section "Sources:".
- Always end your response with this disclaimer on a new line:
  "Disclaimer: This information is for reference only and does not replace professional medical
   advice. Always consult a qualified healthcare professional before making any medical decision."

Context from medication database:
{context}

Question: {question}

Answer:
""".strip()
