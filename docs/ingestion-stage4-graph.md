# Stage 4 — Write to Graph (`graph/graph_builder.py` + `graph/schema.py`)

[← Stage 3](./ingestion-stage3-extract.md) | [Overview](./ingestion-overview.md)

## Purpose

Write extraction dicts into Neo4j as nodes and relationships. All writes use `MERGE` — the operation is fully idempotent.

## Entry Points

```python
from graph.graph_builder import write_extractions
from graph.schema import apply, reset

apply()                          # create constraints + indexes (once)
stats = write_extractions(data)  # load extraction list
# stats = {"records": N, "nodes": N, "relations": N, "failed": N}
```

## Schema Setup (`graph/schema.py`)

Must be run before the first `write_extractions` call.

### Constraints

| Name | Node | Property |
|------|------|----------|
| `drug_name_unique` | `Drug` | `name` |
| `active_ingredient_name_unique` | `ActiveIngredient` | `name` |
| `clinical_concept_name_unique` | `ClinicalConcept` | `name` |

### Indexes

- `drugNameFulltext` — fulltext index on `Drug.name` for fuzzy / case-insensitive lookups.

### `reset()`

Deletes all nodes and relationships (batched by 10 000 rows) and drops all constraints + indexes. Destructive — use only for development resets.

## Node Label System

**Anchor labels** (`Drug`, `ActiveIngredient`) — merged by label + name; get their own MERGE key.

**Clinical concept labels** (`Indication`, `Contraindication`, `AdverseEffect`, `Dose`, `PatientGroup`) — merged as `:ClinicalConcept {name}` first, then the specific label is added (`SET n:Dose`). A node can accumulate multiple labels over time.

**Fallback** — unknown types become `:Entity`.

## Name Normalisation

### `_normalize_label(raw_label) → str`

Removes non-alphanumeric chars, lowercases, looks up alias map, reconstructs PascalCase. Returns one of the seven canonical labels or `"Entity"`.

### `_normalize_name(raw_name, label) → str | None`

| Label | Rule |
|-------|------|
| `Drug` / `ActiveIngredient` | Title-case; strip trailing dosage noise (e.g. "Ibuprofen 400mg" → "Ibuprofen") |
| `Dose` | Must contain `":"` — normalises to `"Title:lowercase"` (e.g. `"Ibuprofen:400mg every 6-8 hours"`); logs warning and drops if format invalid |
| Others | Title-case |

Returns `None` if validation fails; the entity is skipped.

### `_normalize_rel_type(raw_rel) → str`

Strips special chars, uppercases, replaces spaces with underscores. Prepends `REL_` if name starts with a digit.

## Global Label Map

```python
_build_global_label_map(extractions) → dict[str, set[str]]
```

Scans **all** extractions before any writes. Builds `name → set of labels`.

Also registers a "basic-normalised" alias (without label context) so that relation endpoints can be matched even when their declaring entity lives in a different chunk.

This is the key mechanism that enables cross-chunk relation resolution.

## Label Resolution for Relation Endpoints

```python
_resolve_labels(name, local_label_by_name, global_label_map) → list[str]
```

Priority:

1. **Local chunk map** — entity declared in the same extraction dict.
2. **Global map** — if both `Drug` and `ActiveIngredient` present, `Drug` wins.
3. **Fallback** — `["Entity"]`.

## Write Flow

```
Extraction dicts
    └─ _build_global_label_map (scan all extractions)
        └─ per extraction:
            ├─ normalize entities → build local label map
            └─ per relation:
                ├─ normalize endpoint names
                ├─ resolve labels (local → global → Entity)
                ├─ re-normalize with resolved labels
                ├─ queue endpoint nodes
                └─ queue relation row
        └─ single Neo4j session, batch writes:
            ├─ UNWIND Drug / ActiveIngredient nodes
            ├─ UNWIND ClinicalConcept nodes
            └─ UNWIND each relation type
```

All writes happen in one session. Total queries: ~2 for anchor nodes + up to 5 for concept labels + 1 per distinct relation type (max 7) = ~14 queries total regardless of extraction count.

## Isolation rule — Isolated entities dropped

Entities that appear in no relation endpoint are **not written** to the graph. This keeps the graph clean and avoids orphaned nodes.

## Node Properties in Neo4j

```cypher
// Drug / ActiveIngredient
(n:Drug {
    name:       "Ibuprofen",
    created_at: datetime(),
    updated_at: datetime(),
    source_file: "ibuprofen_PIL.pdf",
    page_number: 3,
    doc_type:    "PIL"
})

// ClinicalConcept (e.g. Dose)
(n:ClinicalConcept:Dose {
    name:       "Ibuprofen:400mg every 6-8 hours",
    created_at: datetime(),
    updated_at: datetime(),
    source_file: "ibuprofen_PIL.pdf",
    page_number: 3,
    doc_type:    "PIL"
})
```

## Relationship Properties in Neo4j

```cypher
-[r:HAS_DOSE {
    created_at:       datetime(),
    updated_at:       datetime(),
    doc_type:         "PIL",
    source_citations: ["ibuprofen_PIL.pdf|3", "ibuprofen_PIL.pdf|5"]
}]->
```

`source_citations` accumulates across re-runs; duplicates are removed.

## Return Value

```python
{
    "records":   150,   # extraction dicts processed
    "nodes":     312,   # unique nodes written
    "relations": 489,   # relationships written
    "failed":    2      # extractions skipped due to errors
}
```
