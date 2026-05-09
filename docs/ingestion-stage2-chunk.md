# Stage 2 — Chunk (`ingestion/chunker.py`)

[← Stage 1](./ingestion-stage1-load.md) | [Overview](./ingestion-overview.md) | [Stage 3 →](./ingestion-stage3-extract.md)

## Purpose

Split page-level Documents into overlapping character-bounded chunks and annotate each chunk with its document section type (indication, dose, etc.).

## Entry Point

```python
from ingestion.chunker import chunk_documents

chunks = chunk_documents(docs)  # default: ~800 tokens (3200 chars), ~150 token overlap (600 chars)
```

## Functions

### `build_text_splitter(chunk_size_tokens=800, chunk_overlap_tokens=150, ...) → RecursiveCharacterTextSplitter`

Builds a character-based splitter. Token counts are converted to approximate character counts using a 4 chars ≈ 1 token ratio (so 800 tokens → 3200 chars, 150 overlap → 600 chars).

Separators tried in order: `["\n\n", "\n", ". ", " ", ""]`

---

### `chunk_single_document(document, splitter=None, ...) → list[Document]`

Splits one page Document into chunks.

- Preserves all metadata from the parent page.
- Skips empty chunks.
- Adds per-chunk metadata (see below).
- `chunk_count` is backfilled after filtering empty chunks.

---

### `chunk_documents(documents, chunk_size_tokens=800, chunk_overlap_tokens=150, ...) → list[Document]`

Main entry point.

**Critical:** groups documents by `source_file` before section annotation. This prevents section type from the last page of PDF A bleeding into the first pages of PDF B.

Per PDF group:
1. `annotate_pages(group, propagate=True)` — detects section type per page and propagates forward within the same PDF.
2. Chunks each page using the shared splitter.

## Section Detection

Sections are inferred from page headings/content and annotated as `section_type` metadata (`ingestion/section_splitter.py`).

| `section_type` | Content described |
|----------------|-------------------|
| `indication` | What the drug treats |
| `contraindication` | When the drug must not be used |
| `warning` | Precautions and special populations |
| `adverse_effect` | Side effects |
| `dose` | Dosing instructions |
| `interaction` | Drug-drug interactions |
| `patient_group` | Specific patient populations |
| `storage` | Storage conditions / inactive ingredients |
| `unknown` | TOC page or no recognised header |

### Detection logic (`detect_page_section`)

For each page:

0. **TOC check** — if the page matches a TOC marker regex (`FULL PRESCRIBING INFORMATION: CONTENTS`, `TABLE OF CONTENTS`, `PACKAGE LEAFLET: INFORMATION FOR`, `CONTENTS OF THE PACK`) **or** contains ≥ 5 short numbered lines, it is classified as `unknown` immediately and no further matching is attempted.
1. **Pattern scan** — all header patterns are searched across the full page text. Patterns cover three document formats: EMA Package Leaflet (numbered prose: "1. What X is used for"), US FDA OTC Drug Facts (plain headers: "Uses", "Warnings", "Directions"), and US FDA Prescribing Information (numbered ALL-CAPS: "1 INDICATIONS AND USAGE").
2. **Earliest-match-wins** — every matching pattern records its start position in the text. The `section_type` of the pattern with the **smallest** start position wins. This correctly labels a page whose content starts with adverse-effect text but ends with a "5. How to store" heading as `adverse_effect`.
3. **Boxed WARNING** — `WARNING:` is matched only in the first 300 characters of the page. If found earlier than any other pattern, `warning` wins.
4. **No match** → `unknown`.

### Propagation (`annotate_pages`)

`propagate=True` — if a page is classified `unknown`, it inherits the **previous page's** section type. This handles multi-page sections where only the first page has a header. Propagation resets at each PDF boundary so the last section of one PDF cannot bleed into the first pages of the next.

## Output Metadata per Chunk

```python
# Inherited from page Document:
{
    "source_file": "ibuprofen_PIL.pdf",
    "page_number": 3,
    "doc_type":    "PIL",
    "source_path": "/absolute/path/..."
}

# Added by chunker:
{
    "chunk_index":  2,                         # 1-based position within page
    "chunk_id":     "ibuprofen_PIL.pdf:p3:c2", # unique identifier
    "chunk_count":  5,                          # total non-empty chunks in this page
    "section_type": "dose"                      # from section annotation
}
```

## Data Flow

```
Page-level Documents
    └─ group by source_file
        └─ annotate_pages (section_type, per PDF)
            └─ build character-based splitter (3200 chars / 600 overlap)
                └─ chunk_single_document (per page)
                    └─ skip empty chunks
                        └─ backfill chunk_count
                            → flat list of chunk-level Documents
```
