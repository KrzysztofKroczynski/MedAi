# Streamlit App

**File:** `app/app.py`

Provides the web UI and connects user input to the agent pipeline.

---

## Running

```bash
# Via Docker (recommended)
make app
# or
docker compose up app

# Locally (requires Neo4j running)
streamlit run app/app.py

# Access at
http://localhost:8501
```

---

## UI Layout

- **Sidebar** — model info, session reset button, disclaimer notice
- **Chat area** — conversation history rendered with `st.chat_message`
- **Sources expander** — collapses citations under each assistant message; shows `attribution`, `intent`, and `answer_fragment` per citation

---

## Agent Integration

The app invokes the agent pipeline via `_run_agent_pipeline()`:

```python
def _run():
    async def _ainvoke():
        return await graph.ainvoke(state, config=config)
    return asyncio.run(_ainvoke())

with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
    result = pool.submit(_run).result()
```

`graph.ainvoke` is wrapped in `asyncio.run()` inside a `ThreadPoolExecutor` thread because Streamlit runs its own event loop — calling `asyncio.run()` directly from the main thread raises `RuntimeError: This event loop is already running`.

**Thread ID** (`config["configurable"]["thread_id"]`) is set to `st.session_state.session_id` (a UUID generated once per browser session). The `MemorySaver` checkpointer uses this to persist `session_context` across turns within the same session.

---

## Session State

| Key | Type | Description |
|-----|------|-------------|
| `session_id` | str (UUID) | Thread ID for MemorySaver; reset button generates a new one |
| `messages` | list | Displayed conversation history (separate from agent `messages`) |

---

## Path Setup

`app.py` inserts both the project root and `app/` directory into `sys.path` at startup using `os.path.abspath(__file__)`. This ensures `agent/`, `shared/`, and `graph/` imports resolve correctly whether run locally or inside the Docker container (where the working directory is `/app`).

---

## Safety Display

All assistant responses include the disclaimer appended by `summarizer_node`:

> ⚠️ This information is provided for reference only. Always consult a doctor or pharmacist before making any medication decision.

Citation sources are shown in a collapsible expander, labelled by intent (e.g. "contraindication", "dose") and marked with source type (PDF or web).
