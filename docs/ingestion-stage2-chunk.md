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

Sections are inferred from page headings/content and annotated as `section_type` metadata.

| `section_type` | Content described |
|----------------|-------------------|
| `indication` | What the drug treats |
| `contraindication` | When the drug must not be used |
| `warning` | Precautions and special populations |
| `adverse_effect` | Side effects |
| `dose` | Dosing instructions |
| `interaction` | Drug-drug interactions |
| `patient_group` | Specific patient populations |
| `storage` | Storage conditions |
| `unknown` | Unrecognised section |

`propagate=True` — if a page has no detectable section heading, it inherits the previous page's section type. Propagation resets at each PDF boundary.

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
