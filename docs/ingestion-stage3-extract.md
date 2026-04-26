# Stage 3 — Extract (`ingestion/extractor.py`)

[← Stage 2](./ingestion-stage2-chunk.md) | [Overview](./ingestion-overview.md) | [Stage 4 →](./ingestion-stage4-graph.md)

## Purpose

Call the LLM on each chunk to extract structured entities and relations. Validates output against a schema and retries on errors. Runs chunks in parallel.

## Entry Point

```python
from ingestion.extractor import extract_from_chunks

# Basic usage
extractions = extract_from_chunks(chunks)

# With per-chunk progress callback (called with no arguments after each chunk completes)
completed = [0]
extractions = extract_from_chunks(chunks, on_chunk_done=lambda: completed.__setitem__(0, completed[0] + 1))
```

`on_chunk_done` is an optional zero-argument callable. It is invoked inside the async gather immediately after each chunk's coroutine finishes (whether successfully extracted or skipped). The app UI uses this to stream a live per-chunk progress bar while extraction runs in a background thread.

## Entity Types

| Type | Description | Naming rule |
|------|-------------|-------------|
| `Drug` | Medication product | INN generic name only — no brand names, no dosages |
| `ActiveIngredient` | Pharmacologically active chemical | INN name |
| `Indication` | Condition the drug treats | concise lowercase phrase |
| `Contraindication` | Condition making the drug unsafe | concise lowercase phrase |
| `AdverseEffect` | Unwanted side-effect | concise lowercase phrase |
| `Dose` | Dosing instruction | **`"DrugName:dose detail"`** e.g. `"Ibuprofen:400mg every 6-8 hours"` |
| `PatientGroup` | Patient population with special considerations | lowercase descriptive phrase |

## Relation Types and Allowed Endpoints

| Relation | From | To |
|----------|------|----|
| `CONTAINS` | Drug | ActiveIngredient |
| `INDICATED_FOR` | Drug / ActiveIngredient | Indication |
| `CONTRAINDICATED_IN` | Drug / ActiveIngredient | Contraindication / PatientGroup |
| `HAS_DOSE` | Drug / ActiveIngredient | Dose |
| `INTERACTS_WITH` | Drug / ActiveIngredient | Drug / ActiveIngredient |
| `ALTERNATIVE_FOR` | Drug / ActiveIngredient | Drug / ActiveIngredient |
| `WARNS_FOR` | Drug / ActiveIngredient | AdverseEffect / PatientGroup |

Endpoint type checking only applies when the endpoint name is also declared as an entity in the **same chunk**. Cross-chunk endpoints pass validation (they may be declared elsewhere).

## Section Hints

Each chunk's `section_type` metadata causes a hint to be injected into the extraction prompt, focusing the LLM on relevant entity/relation types:

| `section_type` | Hint injected |
|----------------|---------------|
| `indication` | Focus on Indication + INDICATED_FOR |
| `contraindication` | Focus on Contraindication, PatientGroup + CONTRAINDICATED_IN |
| `warning` | Focus on PatientGroup, AdverseEffect + WARNS_FOR / CONTRAINDICATED_IN |
| `adverse_effect` | Focus on AdverseEffect + WARNS_FOR |
| `dose` | Focus on Dose, PatientGroup + HAS_DOSE |
| `interaction` | Focus on Drug, ActiveIngredient + INTERACTS_WITH |
| `patient_group` | Focus on PatientGroup + WARNS_FOR / CONTRAINDICATED_IN / HAS_DOSE |
| `storage` | Minimal entities expected |
| `unknown` | No hint |

## Retry / Error Handling

Per-chunk extraction follows this flow:

```
Build prompt (chunk text + section hint)
    └─ Call LLM (await llm.ainvoke)
        ├─ Truncated? (finish_reason == "length")
        │      └─ Split chunk in half (at natural boundary)
        │          └─ Extract both halves concurrently (asyncio.gather, max depth 1)
        │              └─ Merge + deduplicate results
        │
        ├─ JSON invalid?
        │      └─ Retry with error-feedback prompt (await llm.ainvoke)
        │
        ├─ Relations violate schema?
        │      └─ Retry with correction prompt (await llm.ainvoke)
        │          └─ Still invalid → drop remaining invalid, keep valid
        │
        └─ All retries fail → log warning, return None (chunk skipped)
```

Retries are sequential **within** a single chunk's coroutine and do not affect other chunks running concurrently.

Deduplication keys: entities by `(type, name)`, relations by `(from, rel, to)`.

## Concurrency

```python
# Default: min(20, total_chunks) concurrent requests
# Override via environment variable:
EXTRACTION_MAX_WORKERS=20
```

`asyncio.gather` fires all chunk coroutines at once; an `asyncio.Semaphore` caps the number of in-flight LLM requests. No threads — the event loop handles IO, so higher concurrency is cheap. Results are collected in original chunk order.

## Output Format

Each successful extraction returns:

```python
{
    "text": "original chunk text",
    "metadata": {
        "source_file":  "ibuprofen_PIL.pdf",
        "page_number":  3,
        "doc_type":     "PIL",
        "chunk_id":     "ibuprofen_PIL.pdf:p3:c2",
        "chunk_index":  2,
        "chunk_count":  5,
        "section_type": "dose"
    },
    "entities": [
        {"type": "Drug",  "name": "Ibuprofen"},
        {"type": "Dose",  "name": "Ibuprofen:400mg every 6-8 hours"}
    ],
    "relations": [
        {"from": "Ibuprofen", "rel": "HAS_DOSE", "to": "Ibuprofen:400mg every 6-8 hours"}
    ],
    "model": "deepseek-chat"
}
```

Failed chunks return `None` and are excluded from the output list.

## Data Flow

```
Chunk-level Documents
    └─ asyncio.gather (all chunks fired concurrently)
        └─ asyncio.Semaphore (caps in-flight requests)
            └─ extract_from_chunk_async (per chunk coroutine)
                ├─ build prompt (text + section hint)
                ├─ await llm.ainvoke
                ├─ truncation → split + asyncio.gather both halves
                ├─ JSON parse + validate
                ├─ relation schema validate
                └─ retry loops (sequential within coroutine)
        → ordered list of extraction dicts (None entries removed)
```

## Caching

`ingest.py` writes results to `data/processed/extractions.json`. Re-running `seed.py` reads from this cache, skipping the LLM step entirely.
