# Agent Tools

Tools are called by the executor node. They are not LangGraph nodes — they are plain functions invoked inside `execute_one()`.

---

## cypher_tool — `agent/tools/cypher_tool.py`

**Purpose:** Execute a parameterised Cypher query against Neo4j and return structured evidence.

**Security:** All templates use `$entity` and `$secondary_entity` as Neo4j query parameters. User-supplied strings are **never** string-interpolated into query text — prevents graph injection.

### Templates

| Intent | Relationship traversed | Notes |
|--------|----------------------|-------|
| `indication` | `INDICATED_FOR` | Matches Drug or ActiveIngredient → Indication |
| `contraindication` | `CONTRAINDICATED_IN` | Matches Drug or ActiveIngredient → Contraindication or PatientGroup |
| `adverse_effect` | `WARNS_FOR` | Drug or ActiveIngredient → AdverseEffect |
| `dose` | `HAS_DOSE` | Drug or ActiveIngredient → Dose |
| `interaction` | `INTERACTS_WITH` | Bidirectional; `$secondary_entity` filters to specific drug pair when set |
| `alternative` | `ALTERNATIVE_FOR` | Bidirectional |
| `patient_group` | `CONTRAINDICATED_IN` / `WARNS_FOR` / `HAS_DOSE` on `PatientGroup` | All relationship types to patient group nodes |
| `general` | Multi-hop: `INDICATED_FOR` + `WARNS_FOR` + `CONTRAINDICATED_IN` | Overview query; returns top 5 per category |

All templates use `toLower() CONTAINS toLower($entity)` for case-insensitive partial matching.

**Limits and ordering:**

| Intent | LIMIT | ORDER BY |
|--------|-------|----------|
| `adverse_effect` | 150 | `size(source_citations) DESC` |
| `indication`, `contraindication`, `dose`, `interaction`, `patient_group` | 100 | `size(source_citations) DESC` |
| `alternative` | 100 | — |
| `general` | 10 | — |

Results are aggregated with `reduce()` so all `source_citations` across matching relationships are merged into a single flat list per (drug, concept) pair before ordering. This ensures that multi-source facts surface first and single-source facts from recently uploaded PDFs are not cut off by the limit.

### Source citations

All templates bind the relationship with a named variable (`[r:...]`) and return `r.source_citations` directly. This is the authoritative multi-source citation list accumulated across all ingestion runs via `ON MATCH SET r.source_citations = r.source_citations + new_citation`.

### Return value

`EvidenceItem` with:
- `source_type`: `"neo4j"`
- `content`: stringified list of record dicts
- `source_citations`: deduplicated `["filename|page"]` list
- `node_names`: values from intent-specific columns (`indication`, `contraindication`, `adverse_effect`, `dose_detail`, `patient_group`, `alternative`, `drug2`)

---

## web_tool — `agent/tools/web_tool.py`

**Purpose:** DuckDuckGo web search fallback when Neo4j returns no results.

**Search engine:** DuckDuckGo via `langchain_community.tools.DuckDuckGoSearchRun` (no API key required).

### Query construction

```
"{entity} {intent with underscores replaced by spaces} {secondary_entity} patient information leaflet"
```

Example for `{entity: "Ibuprofen", intent: "adverse_effect"}`:
```
"Ibuprofen adverse effect patient information leaflet"
```

### Return value

`EvidenceItem` with:
- `source_type`: `"web"`
- `content`: DuckDuckGo result string
- `source_citations`: `["DuckDuckGo web search"]` — fixed attribution prevents empty citation from triggering a NEED_MORE loop
- `node_names`: `[]` (no graph nodes involved)

### When web search runs

The executor calls web search when:
1. The `QueryPlan` item has `source == "web"` — router explicitly flagged it (e.g. very new drugs or brand-only names); Neo4j is skipped entirely
2. Neo4j returned **empty** content — web replaces Neo4j entirely
3. Neo4j returned **thin** content (< `NEO4J_SUPPLEMENT_THRESHOLD` = 300 chars) — web result is appended alongside the Neo4j result
