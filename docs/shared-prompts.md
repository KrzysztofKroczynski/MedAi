# Shared — Prompts (`shared/prompts.py`)

[← Overview](./ingestion-overview.md)

## `ENTITY_EXTRACTION_PROMPT`

Used by: `ingestion/extractor.py`

**Placeholders:**
- `{text}` — chunk content
- `{section_hint}` — optional section-specific guidance injected by the extractor based on `section_type` metadata

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

All entity names must be in English regardless of source text language (Polish, German, etc. are translated).

**Critical rules:**
- `ALTERNATIVE_FOR` only for therapeutic substitutes, not treatments.
- `Dose` and `PatientGroup` must never appear as isolated nodes.
- If nothing is found, return `{"entities": [], "relations": []}`.
