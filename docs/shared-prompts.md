# Shared — Prompts (`shared/prompts.py`)

[← Overview](./ingestion-overview.md)

## Three Prompt Templates

### 1. `ENTITY_EXTRACTION_PROMPT`

Used by: `ingestion/extractor.py`

**Inputs:**
- `{text}` — chunk content
- `{section_hint}` — optional section-specific guidance (injected by extractor based on `section_type`)

**Output:** Strictly valid JSON, no markdown wrapping.

```json
{
  "entities": [{"type": "Drug", "name": "Ibuprofen"}],
  "relations": [{"from": "Ibuprofen", "rel": "HAS_DOSE", "to": "Ibuprofen:400mg every 6-8 hours"}]
}
```

**Naming rules enforced in the prompt:**

| Type | Rule |
|------|------|
| `Drug` | INN generic name only — no brand names, no dosages |
| `Dose` | Format `"DrugName:dose detail"` — always linked via `HAS_DOSE` |
| `PatientGroup` | Lowercase descriptive phrase — always linked to a drug via a relation |
| Others | Concise lowercase phrase |

**Critical rules:**
- `ALTERNATIVE_FOR` only for therapeutic substitutes, not treatments.
- `Dose` and `PatientGroup` must never appear as isolated nodes.

---

### 2. `CYPHER_GENERATION_PROMPT`

Used by: `rag/retriever.py`

**Input:** `{question}` — user's natural-language question.

**Output:** Raw Cypher `MATCH` + `RETURN` query only. No `CREATE`, `MERGE`, `SET`, or `DELETE`.

**Schema guidance embedded in the prompt:**
- Anchor labels: `Drug`, `ActiveIngredient`
- Clinical concepts: `Indication`, `Contraindication`, `AdverseEffect`, `Dose`, `PatientGroup` (all also carry `:ClinicalConcept`)
- Relationship property `source_citations` (list of `"file|page"` strings)

**Key rules:**
- Case-insensitive matching: `toLower(n.name) CONTAINS toLower('keyword')`
- Always include `source_citations` in `RETURN`
- `LIMIT 50`
- Return raw Cypher only — no markdown.

---

### 3. `QA_PROMPT`

Used by: `rag/qa.py`

**Inputs:**
- `{context}` — formatted query results from Neo4j
- `{question}` — user's question

**Output:** Medical answer grounded strictly in the provided context.

**Rules:**
- Use **only** context information — no training data.
- If context is empty: refuse to answer with a disclaimer.
- Include source citations (`filename|page`).
- Always end with a medical disclaimer.

**Refusal message (empty context):**
> "The available medication documents do not contain sufficient information to answer this question. Please consult a doctor or pharmacist."
