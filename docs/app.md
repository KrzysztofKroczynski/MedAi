# Streamlit App

**File:** `app/app.py`

Provides the web UI and connects user input to the agent pipeline. Also includes an in-app PDF ingestion workflow so new medication documents can be added without touching the command line.

---

## Running

```bash
# Via Docker (recommended)
make up
# or
docker compose up neo4j app -d

# Locally (requires Neo4j running)
uv run streamlit run app/app.py

# Access at
http://localhost:8501
```

---

## UI Layout

### Normal chat mode

- **Sidebar** — session info and **📤 Add New PDF** upload section (see below)
- **Chat area** — conversation history rendered with `st.chat_message`
- **Sources expander** — collapses citations under each assistant message; shows `attribution`, `intent`, and `verbatim` text per citation
- **Agent trace expander** — visible when `?debug=1` is in the URL; shows per-node execution details for the last query

### Ingestion mode

When a PDF is being ingested the chat area is replaced by a full-width **ingestion panel** (see below). The sidebar upload section remains visible.

---

## PDF Upload & Ingestion

### Sidebar upload

`_render_upload_sidebar()` renders a `st.file_uploader` accepting `.pdf` files.
Clicking **🚀 Ingest PDF**:
1. Saves the uploaded bytes to `data/pdfs/<filename>`
2. Sets `ingestion_active = True` in session state
3. Calls `st.rerun()` to switch to ingestion mode

If the file already exists in `data/pdfs/` a warning is shown before the button.

### Ingestion panel (`_render_ingestion_panel`)

Runs the full ingestion pipeline inline, displaying a live debug panel with two progress indicators:

| Progress element | What it tracks |
|------------------|----------------|
| Overall `st.progress` bar | Advances in 5 steps: 0 → 15 → 30 → 75 → 82 → 100 % |
| Per-chunk `st.progress` bar | Updates every 0.4 s via a poll loop while extraction runs in a `ThreadPoolExecutor` thread |

**Pipeline stages shown:**

| # | Stage | Details shown |
|---|-------|---------------|
| 1 | Load PDF | Page count |
| 2 | Chunk text | Chunk count, token parameters |
| 3 | Extract entities | Per-chunk progress bar; on completion: record count, entity/relation totals, deduplicated entity names grouped by type (up to 30 per type) |
| 4 | Save cache | Path to `data/processed/extractions.json`, total record count after merge |
| 5 | Write to Neo4j | Node count, relation count, warning if any records failed |

The `st.status` context manager marks the pipeline **complete** (green) or **error** (red) and keeps the log expanded so the user can read every step.

After the pipeline finishes a summary row of `st.metric` cards is shown (pages / chunks / nodes / relations), plus an expandable entity-type breakdown.

The **← Back to chat** button clears all ingestion session state and returns to chat mode.

### Cache behaviour

`_append_to_extraction_cache(new_extractions)` loads the existing `data/processed/extractions.json` (if present), appends the new records, and writes the merged list back. This is non-destructive: previous extractions from other PDFs are preserved.

---

## Agent Integration

The app invokes the agent pipeline via `_run_agent_pipeline()`:

```python
def _run():
    async def _astream():
        async for chunk in graph.astream(state, config=config, stream_mode="updates"):
            ...
    asyncio.run(_astream())

with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
    pool.submit(_run).result()
```

`graph.astream` is wrapped in `asyncio.run()` inside a `ThreadPoolExecutor` thread because Streamlit's script thread may already have an event loop — calling `asyncio.run()` directly would raise `RuntimeError: This event loop is already running`.

The same pattern is used for extraction during in-app ingestion: `extract_from_chunks` (which calls `asyncio.run` internally) runs in a `ThreadPoolExecutor` thread while the main Streamlit thread polls a shared counter to update the progress bar.

**Thread ID** (`config["configurable"]["thread_id"]`) is set to `st.session_state.session_id` (a UUID generated once per browser session). The `MemorySaver` checkpointer uses this to persist `session_context` across turns within the same session.

---

## Session State

### Chat state

| Key | Type | Description |
|-----|------|-------------|
| `session_id` | `str` (UUID) | Thread ID for MemorySaver |
| `messages` | `list` | Displayed conversation history |
| `agent_trace` | `list` | Trace from the last agent run (used by `?debug=1` panel) |

### Ingestion state

| Key | Type | Description |
|-----|------|-------------|
| `ingestion_active` | `bool` | When `True`, ingestion panel replaces the chat UI |
| `ingestion_pdf_path` | `Path` | Absolute path to the saved PDF |
| `ingestion_filename` | `str` | Original upload filename |
| `ingestion_done` | `bool` | Set after the pipeline completes; prevents re-running on rerender |
| `ingestion_result` | `dict` | Stats dict: `pages`, `chunks`, `extractions`, `nodes`, `relations`, `failed`, `entity_types` |

---

## Debug Panel (`?debug=1`)

Activate by appending `?debug=1` to the URL. Renders `_render_memory_panel()` in the sidebar:

- **Session Context** — JSON from the LangGraph `MemorySaver` checkpointer
- **Message History** — each turn expandable with full content
- **Last Run — Agent Trace** — per-node expandable sections with guardrail label, query plan, evidence items, decision, citations, and answer preview

The agent trace is also surfaced inline below the assistant message in the chat area when `?debug=1` is active.

---

## Path Setup

`app.py` inserts both the project root and `app/` directory into `sys.path` at startup using `os.path.abspath(__file__)`. This ensures `agent/`, `shared/`, `graph/`, and `ingestion/` imports resolve correctly whether run locally or inside the Docker container (where the working directory is `/app`).

---

## Static PDF Serving

`_sync_static_pdfs()` mirrors `data/pdfs/` → `app/static/pdfs/` on startup and again after each in-app ingestion. Files are copied only when size or mtime differs. Streamlit serves them at `/app/static/pdfs/<filename>` with `#page=N` anchors for citation links.

---

## Safety Display

All assistant responses include the disclaimer appended by `summarizer_node`:

> ⚠️ This information is provided for reference only. Always consult a doctor or pharmacist before making any medication decision.

Citation sources are shown in a collapsible expander, labelled by intent (e.g. "contraindication", "dose") and marked with source type (PDF or web).
