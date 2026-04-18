# Stage 1 — Load (`ingestion/loader.py`)

[← Overview](./ingestion-overview.md) | [Stage 2 →](./ingestion-stage2-chunk.md)

## Purpose

Read all PDFs from `data/pdfs/`, produce one LangChain `Document` per non-blank page, and attach normalised metadata.

## Entry Point

```python
from ingestion.loader import load_pdfs

docs = load_pdfs()          # loads from data/pdfs/ by default
docs = load_pdfs("/my/dir") # explicit directory
```

## Functions

### `resolve_pdf_dir(pdf_dir) → Path`

Priority order for the PDF directory:

1. Explicit function argument
2. `PDF_DIR` environment variable
3. Default: `data/pdfs`

---

### `resolve_doc_type(filename: str) → str`

Infers document type from filename keywords.

| Keyword(s) in filename | `doc_type` |
|------------------------|------------|
| `pil`, `leaflet` | `PIL` |
| `smpc`, `spc` | `SmPC` |
| `prescribing` | `PrescribingInformation` |
| `interaction` | `InteractionReference` |
| `formulary` | `Formulary` |
| *(no match)* | `Unknown` |

---

### `iter_pdf_files(pdf_dir, recursive=True) → Iterable[Path]`

Yields PDF paths in sorted order.
`recursive=True` → `**/*.pdf` (subdirectories included).
`recursive=False` → top-level only.

---

### `load_single_pdf(pdf_path) → list[Document]`

Loads one PDF with `PyPDFLoader`.

- Returns **one Document per non-blank page**.
- Page numbers are converted to **1-based**.
- Blank pages (whitespace-only text) are skipped.

---

### `load_pdfs(pdf_dir=None, recursive=True, fail_fast=False) → list[Document]`

Main entry point. Calls `load_single_pdf` for every PDF found.

- `fail_fast=False` — logs errors for corrupt PDFs and continues.
- `fail_fast=True` — stops on the first error (useful for debugging).

Returns a flat list of all page-level Documents.

## Output Metadata per Document

```python
{
    "source_file": "ibuprofen_PIL.pdf",   # basename only
    "page_number": 3,                      # 1-based
    "doc_type":    "PIL",                  # resolved from filename
    "source_path": "/absolute/path/..."   # full path
}
```

## Data Flow

```
PDF files (sorted, recursive)
    └─ PyPDFLoader (per file)
        └─ page-level Documents
            └─ skip blank pages
                └─ attach metadata
                    → flat list of Documents
```
