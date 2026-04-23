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
All templates use `LIMIT 50` (except `general` which uses `LIMIT 10`).

### Source citation fallback

Relationship properties (`r.source_citations`) are preferred. If absent, node properties (`source_file`, `page_number`) are used to construct `"filename|page"` strings. This handles relationship types that were written without a relationship variable (e.g. `CONTRAINDICATED_IN`).

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

The executor calls web search if:
1. Neo4j returned empty content, **or**
2. The `QueryPlan` item has `source == "web"` (router explicitly flagged it as a web query — e.g. very new drugs or brand-only names)
