"""Streamlit chat UI for MedGraph AI — multi-agent backend."""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import os
import shutil
import sys
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote

import streamlit as st

# Ensure project root (parent of app/) is on sys.path so `agent` and `shared`
# are importable regardless of working directory or how Streamlit loads the file.
_HERE = Path(os.path.abspath(__file__)).parent          # .../MedAi/app
_ROOT = _HERE.parent                                     # .../MedAi
for _p in (_ROOT, _HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


logger = logging.getLogger(__name__)

DEFAULT_DISCLAIMER = (
    "Medical disclaimer: This assistant is for informational purposes only and "
    "does not replace professional medical advice, diagnosis, or treatment."
)

PROJECT_ROOT = _ROOT
DATA_PDFS_DIR = PROJECT_ROOT / "data" / "pdfs"
STATIC_PDFS_DIR = _HERE / "static" / "pdfs"

# Node display metadata: (icon, label)
_NODE_META: dict[str, tuple[str, str]] = {
    "guardrail":        ("🛡️", "Guardrail"),
    "router":           ("🗺️", "Router"),
    "executor":         ("🔍", "Executor"),
    "decision":         ("🧠", "Decision"),
    "citation":         ("📎", "Citation Builder"),
    "summarizer":       ("✍️", "Summarizer"),
    "reject_injection": ("🚫", "Rejected — Injection"),
    "reject_offtopic":  ("🚫", "Rejected — Off-topic"),
}


def _sync_static_pdfs() -> None:
    """Mirror data/pdfs -> static/pdfs for clickable source links in Streamlit."""
    if not DATA_PDFS_DIR.exists():
        return

    STATIC_PDFS_DIR.mkdir(parents=True, exist_ok=True)

    for pdf_file in DATA_PDFS_DIR.rglob("*.pdf"):
        target = STATIC_PDFS_DIR / pdf_file.name
        should_copy = (
            not target.exists()
            or pdf_file.stat().st_size != target.stat().st_size
            or int(pdf_file.stat().st_mtime) != int(target.stat().st_mtime)
        )
        if should_copy:
            shutil.copy2(pdf_file, target)


def _pdf_source_url(file_name: str, page_number: int | None = None) -> str:
    """Build Streamlit static URL for a PDF file, optionally jumping to page."""
    base = f"/app/static/pdfs/{quote(file_name, safe='')}"
    return f"{base}#page={page_number}" if page_number else base


# ---------------------------------------------------------------------------
# Agent trace helpers
# ---------------------------------------------------------------------------

def _format_node_trace(node_name: str, updates: dict) -> dict:
    """Extract key facts from a node's state update for display."""
    info: dict[str, Any] = {"node": node_name}

    if node_name == "guardrail":
        label = updates.get("guardrail_label", "")
        info["label"] = label
        info["summary"] = f"Classified input as **{label}**"

    elif node_name == "router":
        plan = updates.get("query_plan", [])
        info["query_plan"] = plan
        info["summary"] = f"Decomposed into **{len(plan)}** query item(s)"

    elif node_name == "executor":
        buffer = updates.get("evidence_buffer", [])
        neo4j_hits = [e for e in buffer if e.get("source_type") == "neo4j"]
        web_hits = [e for e in buffer if e.get("source_type") == "web"]
        info["evidence"] = [
            {
                "query_id": e.get("query_id"),
                "source": e.get("source_type"),
                "nodes": e.get("node_names", []),
                "citations": e.get("source_citations", []),
                "content_chars": len(str(e.get("content", ""))),
            }
            for e in buffer
        ]
        info["summary"] = (
            f"Retrieved **{len(buffer)}** evidence items — "
            f"Neo4j: {len(neo4j_hits)}, Web: {len(web_hits)}"
        )

    elif node_name == "decision":
        decision = updates.get("llm_decision", "")
        iteration = updates.get("iteration", "?")
        more = updates.get("next_query_plan", [])
        info["decision"] = decision
        info["iteration"] = iteration
        info["next_queries"] = more
        color = "green" if decision == "SUFFICIENT" else "orange"
        info["summary"] = f":{color}[**{decision}**] — iteration {iteration}"

    elif node_name == "citation":
        citations = updates.get("citations", [])
        found = [c for c in citations if c.get("found")]
        info["citations"] = citations
        info["summary"] = f"Built **{len(found)}/{len(citations)}** citations"

    elif node_name == "summarizer":
        ctx = updates.get("session_context", {})
        answer = updates.get("final_answer", "")
        info["session_context"] = ctx
        info["answer_preview"] = answer[:400] + ("…" if len(answer) > 400 else "")
        info["summary"] = f"Generated answer (**{len(answer)}** chars)"

    elif node_name in ("reject_injection", "reject_offtopic"):
        info["summary"] = f"Request **rejected** — {node_name.replace('reject_', '')}"
        info["reason"] = updates.get("final_answer", "")

    else:
        info["summary"] = "Node completed"
        info["raw"] = {k: str(v)[:300] for k, v in updates.items() if k != "messages"}

    return info


def _render_agent_trace(trace: list[dict], container: Any) -> None:
    """Render the agent execution trace into a Streamlit container."""
    if not trace:
        container.info("No trace available — run a query first.")
        return

    for step in trace:
        node = step.get("node", "unknown")
        icon, label = _NODE_META.get(node, ("⚙️", node))
        summary = step.get("summary", "")

        with container.expander(f"{icon} **{label}** — {summary}", expanded=False):
            # Guardrail
            if node == "guardrail":
                st.write(f"**Label:** `{step.get('label', '')}`")

            # Router
            elif node == "router":
                plan = step.get("query_plan", [])
                for item in plan:
                    se = item.get("secondary_entity", "")
                    entity_str = item["entity"] + (f" ↔ {se}" if se else "")
                    st.markdown(
                        f"- `{item['query_id']}` **{item['intent']}** — "
                        f"{entity_str} _(source: {item['source']})_"
                    )

            # Executor
            elif node == "executor":
                for ev in step.get("evidence", []):
                    src_icon = "🗄️" if ev["source"] == "neo4j" else "🌐"
                    nodes_str = ", ".join(ev["nodes"][:5]) or "—"
                    st.markdown(
                        f"{src_icon} `{ev['query_id']}` · **{ev['source']}** · "
                        f"{ev['content_chars']} chars · nodes: _{nodes_str}_"
                    )
                    if ev["citations"]:
                        for cit in ev["citations"][:3]:
                            st.caption(f"  📄 {cit}")

            # Decision
            elif node == "decision":
                st.write(f"**Decision:** `{step.get('decision')}`")
                st.write(f"**Iteration:** {step.get('iteration')}")
                more = step.get("next_queries", [])
                if more:
                    st.write("**Additional queries planned:**")
                    for q in more:
                        st.markdown(f"- `{q['query_id']}` {q['intent']} / {q['entity']}")

            # Citation builder
            elif node == "citation":
                for c in step.get("citations", []):
                    found_icon = "✅" if c.get("found") else "❌"
                    st.markdown(
                        f"{found_icon} `{c.get('query_id')}` **{c.get('intent')}** — "
                        f"{c.get('verbatim', '')[:120]}"
                    )
                    if c.get("attribution"):
                        st.caption(f"  ↳ {c['attribution']}")

            # Summarizer
            elif node == "summarizer":
                st.write("**Session context after this turn:**")
                st.json(step.get("session_context", {}))
                st.write("**Answer preview:**")
                st.text(step.get("answer_preview", ""))

            # Rejections
            elif node in ("reject_injection", "reject_offtopic"):
                st.write(step.get("reason", ""))

            # Fallback
            else:
                st.json(step.get("raw", {}))


# ---------------------------------------------------------------------------
# Agent pipeline
# ---------------------------------------------------------------------------

def _run_agent_pipeline(user_input: str, session_id: str) -> dict[str, Any]:
    """Invoke the LangGraph multi-agent pipeline and return a result dict."""
    try:
        from agent.graph import graph
        from langchain_core.messages import HumanMessage
    except Exception as exc:
        logger.exception("Agent graph unavailable")
        return {
            "answer": (
                f"Agent backend unavailable: {exc}\n\n"
                "Run `pip install -r requirements.txt` and ensure the `agent/` "
                "package is on the Python path."
            ),
            "citations": [],
            "no_data": True,
        }

    state = {
        "messages": [HumanMessage(content=user_input)],
        "session_id": session_id,
        "session_context": {},  # checkpointer restores persisted context
        "guardrail_label": "",
        "query_plan": [],
        "iteration": 0,
        "evidence_buffer": [],
        "llm_decision": "",
        "next_query_plan": [],
        "citations": [],
        "final_answer": "",
        "error": None,
    }
    config = {"configurable": {"thread_id": session_id}}

    trace: list[dict] = []
    final_answer = ""
    citations: list = []

    # Run async graph.astream in a dedicated thread so it gets a clean event loop,
    # avoiding conflicts with Streamlit's own event loop.
    def _run():
        nonlocal final_answer, citations

        async def _astream():
            nonlocal final_answer, citations
            async for chunk in graph.astream(state, config=config, stream_mode="updates"):
                for node_name, updates in chunk.items():
                    trace.append(_format_node_trace(node_name, updates))
                    if "final_answer" in updates and updates["final_answer"]:
                        final_answer = updates["final_answer"]
                    if "citations" in updates:
                        citations = updates["citations"]

        asyncio.run(_astream())

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(_run).result()

    # Persist trace for the debug panel
    st.session_state["agent_trace"] = trace

    return {
        "answer": final_answer or "No answer generated.",
        "citations": citations,
        "no_data": not final_answer,
    }


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------

def _render_citations(citations: list[dict[str, Any]]) -> None:
    """Render structured CitationItem list returned by the agent."""
    if not citations:
        return

    for c in citations:
        if c.get("found"):
            st.markdown(f"**{c.get('intent', '')}** — {c.get('verbatim', '')}")

            source_links = c.get("source_links", [])
            if source_links:
                for link in source_links:
                    if link.get("source_type") == "pdf" and link.get("file"):
                        file_name = str(link.get("file", ""))
                        page_number = link.get("page")
                        label = link.get("label") or (
                            f"{file_name}, page {page_number}" if page_number else file_name
                        )

                        if (STATIC_PDFS_DIR / file_name).exists():
                            st.markdown(f"- [{label}]({_pdf_source_url(file_name, page_number)})")
                        else:
                            st.markdown(f"- {label} _(PDF file not available)_")
                    elif link.get("source_type") == "web" and link.get("url"):
                        label = link.get("label") or link.get("url")
                        st.markdown(f"- [{label}]({link.get('url')})")
            elif c.get("attribution"):
                st.markdown(f"_{c.get('attribution')}_")


def _get_agent_memory(session_id: str) -> dict[str, Any] | None:
    """Fetch current checkpointer state for the session."""
    try:
        from agent.graph import graph
        config = {"configurable": {"thread_id": session_id}}
        snapshot = graph.get_state(config)
        if snapshot is None:
            return None
        values = snapshot.values
        messages = values.get("messages", [])
        serialized_messages = []
        for m in messages:
            role = getattr(m, "type", type(m).__name__)
            serialized_messages.append({"role": role, "content": m.content})
        return {
            "session_id": session_id,
            "session_context": values.get("session_context", {}),
            "messages": serialized_messages,
            "turn_count": values.get("session_context", {}).get("turn_count", 0),
        }
    except Exception as exc:
        return {"error": str(exc)}


def _render_memory_panel(session_id: str) -> None:
    """Render memory inspector in the sidebar (only when ?debug=1)."""
    st.sidebar.title("🧠 Memory Inspector")
    st.sidebar.caption(f"Session: `{session_id}`")

    # --- Session context ---
    memory = _get_agent_memory(session_id)
    if memory is None:
        st.sidebar.info("No checkpointer state yet — ask a question first.")
    elif "error" in memory:
        st.sidebar.error(f"Error reading state: {memory['error']}")
    else:
        ctx = memory.get("session_context", {})
        st.sidebar.subheader("Session Context")
        st.sidebar.json(ctx if ctx else {"note": "empty — no turns completed yet"})

        msgs = memory.get("messages", [])
        st.sidebar.subheader(f"Message History ({len(msgs)} messages)")
        for i, m in enumerate(msgs):
            role = m.get("role", "unknown")
            content = m.get("content", "")
            icon = "🧑" if role == "human" else "🤖"
            with st.sidebar.expander(f"{icon} [{i+1}] {role}", expanded=False):
                st.text(content[:2000] + ("…" if len(content) > 2000 else ""))

    # --- Last run trace ---
    trace = st.session_state.get("agent_trace", [])
    st.sidebar.subheader(f"Last Run — Agent Trace ({len(trace)} steps)")
    _render_agent_trace(trace, st.sidebar)


def _render_assistant_message(payload: dict[str, Any], debug: bool = False) -> None:
    answer = str(payload.get("answer", "")).strip()
    citations = payload.get("citations", [])
    is_no_data = bool(payload.get("no_data"))

    if is_no_data and not answer:
        st.warning("No data available to answer this question.")
    else:
        st.markdown(answer or "No answer generated.")

    if citations:
        with st.expander("Sources"):
            _render_citations(citations if isinstance(citations, list) else [])

    if debug:
        trace = st.session_state.get("agent_trace", [])
        if trace:
            with st.expander(f"🔬 Agent trace ({len(trace)} steps)", expanded=False):
                _render_agent_trace(trace, st)


# ---------------------------------------------------------------------------
# PDF ingestion helpers
# ---------------------------------------------------------------------------

def _append_to_extraction_cache(new_extractions: list[dict]) -> int:
    """Merge new extractions into the existing cache. Returns total record count."""
    cache_path = PROJECT_ROOT / "data" / "processed" / "extractions.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    existing: list[dict] = []
    if cache_path.exists():
        try:
            with cache_path.open("r", encoding="utf-8") as fp:
                existing = json.load(fp)
        except Exception:
            existing = []

    merged = existing + new_extractions
    with cache_path.open("w", encoding="utf-8") as fp:
        json.dump(merged, fp, ensure_ascii=False, indent=2)
    return len(merged)


def _render_upload_sidebar() -> None:
    """Sidebar section: upload a new PDF and trigger ingestion."""
    with st.sidebar:
        st.divider()
        st.subheader("📤 Add New PDF")

        uploaded = st.file_uploader(
            "Upload medication PDF",
            type=["pdf"],
            key="pdf_uploader",
        )

        if uploaded is not None:
            dest = DATA_PDFS_DIR / uploaded.name
            if dest.exists():
                st.warning(f"`{uploaded.name}` already exists — will overwrite and re-ingest.")

            if st.button("🚀 Ingest PDF", type="primary", use_container_width=True):
                DATA_PDFS_DIR.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(uploaded.getvalue())
                st.session_state["ingestion_active"] = True
                st.session_state["ingestion_pdf_path"] = dest
                st.session_state["ingestion_filename"] = uploaded.name
                st.session_state.pop("ingestion_done", None)
                st.session_state.pop("ingestion_result", None)
                st.rerun()


def _render_ingestion_panel() -> None:
    """Full-screen ingestion panel with stage-by-stage progress."""
    pdf_path: Path = st.session_state["ingestion_pdf_path"]
    filename: str = st.session_state["ingestion_filename"]

    st.title("💊 MedGraph AI — Ingesting PDF")
    st.caption(f"File: `{filename}`")

    # Pipeline only runs once per ingestion session
    if not st.session_state.get("ingestion_done"):
        overall = st.progress(0, text="Starting…")

        with st.status("Running ingestion pipeline…", expanded=True) as pipeline_status:

            # ── Stage 1: Load ────────────────────────────────────────────
            st.write("📄 **Stage 1 / 5** — Loading PDF pages…")
            from ingestion.loader import load_single_pdf
            docs = load_single_pdf(pdf_path)
            overall.progress(15, text="PDF loaded")

            if not docs:
                pipeline_status.update(label="❌ Failed — no pages loaded", state="error")
                st.error("No pages could be read from the PDF. Check the file and try again.")
                return

            st.write(f"✅ Loaded **{len(docs)}** pages")

            # ── Stage 2: Chunk ───────────────────────────────────────────
            st.write("✂️ **Stage 2 / 5** — Chunking text…")
            from ingestion.chunker import chunk_documents
            chunks = chunk_documents(docs)
            overall.progress(30, text="Text chunked")

            if not chunks:
                pipeline_status.update(label="❌ Failed — no chunks generated", state="error")
                st.error("Text chunking produced no output.")
                return

            st.write(f"✅ Generated **{len(chunks)}** chunks (800 tokens, 150 overlap)")

            # ── Stage 3: LLM entity extraction ──────────────────────────
            st.write(f"🧠 **Stage 3 / 5** — Extracting entities from **{len(chunks)}** chunks…")
            st.caption("Each chunk is sent to the LLM concurrently. This may take several minutes.")

            from ingestion.extractor import extract_from_chunks

            total_chunks = len(chunks)
            completed: list[int] = [0]

            def _on_chunk_done() -> None:
                completed[0] += 1

            extraction_bar = st.progress(0.0, text=f"0 / {total_chunks} chunks")

            def _run_extract() -> list[dict]:
                return extract_from_chunks(chunks, on_chunk_done=_on_chunk_done)

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(_run_extract)
                while not future.done():
                    done = completed[0]
                    frac = done / total_chunks if total_chunks else 1.0
                    extraction_bar.progress(frac, text=f"{done} / {total_chunks} chunks")
                    time.sleep(0.4)
                extractions = future.result()

            extraction_bar.progress(1.0, text=f"{len(extractions)} / {total_chunks} chunks")
            overall.progress(75, text="Extraction complete")

            entity_count = sum(len(e.get("entities", [])) for e in extractions)
            rel_count = sum(len(e.get("relations", [])) for e in extractions)
            st.write(
                f"✅ Extracted **{len(extractions)}** records — "
                f"**{entity_count}** entities, **{rel_count}** relations"
            )
            if rel_count == 0 and entity_count > 0:
                st.warning(
                    "⚠️ **0 relations extracted.** Entities were found but no relationships between them. "
                    "Only nodes linked by at least one relation are written to Neo4j — "
                    "if this stays at 0, the graph will not be updated. "
                    "This often happens with non-English PDFs or very short/image-only documents."
                )

            # Deduplicated entity names grouped by type
            entity_types: dict[str, list[str]] = {}
            for ext in extractions:
                for ent in ext.get("entities", []):
                    t = ent.get("type", "Unknown")
                    raw_name = ent.get("name", "")
                    name = raw_name.strip().title() if raw_name else ""
                    if name:
                        entity_types.setdefault(t, [])
                        if name not in entity_types[t]:
                            entity_types[t].append(name)
            if entity_types:
                with st.expander("🔬 Extracted entities by type", expanded=True):
                    for etype, names in sorted(entity_types.items()):
                        names_sorted = sorted(names)
                        preview = ", ".join(f"`{n}`" for n in names_sorted[:30])
                        overflow = f" _+{len(names_sorted) - 30} more_" if len(names_sorted) > 30 else ""
                        st.markdown(f"**{etype}** ({len(names_sorted)}): {preview}{overflow}")

            # ── Stage 4: Save JSON cache ─────────────────────────────────
            st.write("💾 **Stage 4 / 5** — Saving extraction cache…")
            total_cached = _append_to_extraction_cache(extractions)
            overall.progress(82, text="Cache saved")
            st.write(f"✅ Cache updated — {total_cached} total records in `data/processed/extractions.json`")

            # ── Stage 5: Write to Neo4j ──────────────────────────────────
            st.write("🗄️ **Stage 5 / 5** — Writing to Neo4j knowledge graph…")
            from graph.graph_builder import write_extractions
            from graph.schema import apply as apply_schema

            apply_schema()
            stats = write_extractions(extractions)
            overall.progress(100, text="Done!")

            nodes_written = stats.get("nodes", 0)
            rels_written = stats.get("relations", 0)
            st.write(
                f"✅ Neo4j: **{nodes_written}** nodes, **{rels_written}** relations written"
            )
            if stats.get("failed"):
                st.warning(f"{stats['failed']} records failed to write — check the logs.")

            if nodes_written == 0 and len(extractions) > 0:
                st.error(
                    "⚠️ **0 nodes written to Neo4j.** "
                    "The graph builder only writes nodes that appear as endpoints of at least one relation. "
                    f"The LLM extracted **{entity_count}** entities but **{rel_count}** relations from this PDF. "
                    + ("No valid relations were found — check that the PDF language and content "
                       "are supported by the extraction prompt." if rel_count == 0 else
                       "All extracted relations may have failed schema validation — check the logs.")
                )
            else:
                # Verify what actually landed in Neo4j for this file
                try:
                    from shared.neo4j_client import get_driver
                    driver = get_driver()
                    with driver.session() as _sess:
                        verify_result = _sess.run(
                            "MATCH (n) WHERE n.source_file = $f "
                            "RETURN labels(n) AS lbls, count(n) AS cnt "
                            "ORDER BY cnt DESC",
                            f=filename,
                        )
                        rows = verify_result.data()
                    if rows:
                        breakdown = ", ".join(
                            f"{r['lbls'][-1]}: {r['cnt']}" for r in rows
                            if r["lbls"]
                        )
                        st.caption(f"Neo4j verification — nodes from `{filename}`: {breakdown}")
                    else:
                        st.warning(
                            f"Neo4j verification: no nodes found with `source_file = {filename}`. "
                            "The write may have matched existing nodes from other sources."
                        )
                except Exception as _ve:
                    st.caption(f"Neo4j verification skipped: {_ve}")

            pipeline_status.update(
                label=f"{'✅' if nodes_written > 0 else '⚠️'} Ingestion complete — {filename}",
                state="complete" if nodes_written > 0 else "error",
            )

        _sync_static_pdfs()

        st.session_state["ingestion_done"] = True
        st.session_state["ingestion_result"] = {
            "pages": len(docs),
            "chunks": len(chunks),
            "extractions": len(extractions),
            "nodes": stats.get("nodes", 0),
            "relations": stats.get("relations", 0),
            "failed": stats.get("failed", 0),
            "entity_types": entity_types,
        }

    # Results summary (shown even after rerender)
    result = st.session_state.get("ingestion_result", {})
    if result:
        st.success(f"**{filename}** has been added to the knowledge graph!")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Pages", result.get("pages", 0))
        col2.metric("Chunks", result.get("chunks", 0))
        col3.metric("Nodes written", result.get("nodes", 0))
        col4.metric("Relations", result.get("relations", 0))

        if result.get("entity_types"):
            with st.expander("Extracted entity breakdown"):
                for etype, names in sorted(result["entity_types"].items()):
                    names_sorted = sorted(names)
                    preview = ", ".join(f"`{n}`" for n in names_sorted[:30])
                    overflow = f" _+{len(names_sorted) - 30} more_" if len(names_sorted) > 30 else ""
                    st.markdown(f"**{etype}** ({len(names_sorted)}): {preview}{overflow}")

    st.divider()
    if st.button("← Back to chat", type="primary"):
        for key in ("ingestion_active", "ingestion_done", "ingestion_result",
                    "ingestion_pdf_path", "ingestion_filename"):
            st.session_state.pop(key, None)
        st.rerun()


def main() -> None:
    _sync_static_pdfs()

    st.set_page_config(page_title="MedGraph AI", page_icon="💊", layout="centered")

    if "session_id" not in st.session_state:
        st.session_state["session_id"] = str(uuid.uuid4())
    if "messages" not in st.session_state:
        st.session_state["messages"] = []

    # Ingestion mode — replaces chat UI while a PDF is being processed
    if st.session_state.get("ingestion_active"):
        _render_upload_sidebar()
        _render_ingestion_panel()
        return

    _render_upload_sidebar()

    st.title("💊 MedGraph AI")
    st.write("Ask medication questions in natural language.")

    # Secret debug panel — activate by adding ?debug=1 to the URL
    debug = st.query_params.get("debug") == "1"
    if debug:
        _render_memory_panel(st.session_state["session_id"])

    for message in st.session_state["messages"]:
        role = message.get("role", "assistant")
        with st.chat_message(role):
            if role == "assistant":
                _render_assistant_message(message, debug=debug)
            else:
                st.markdown(message.get("content", ""))

    user_question = st.chat_input("E.g., Can Ibuprofen interact with Warfarin?")
    if not user_question:
        return

    st.session_state["messages"].append({"role": "user", "content": user_question})
    with st.chat_message("user"):
        st.markdown(user_question)

    with st.chat_message("assistant"):
        with st.spinner("Searching medication documents..."):
            try:
                assistant_payload = _run_agent_pipeline(
                    user_question, st.session_state["session_id"]
                )
            except Exception as exc:
                logger.exception("Agent pipeline failed")
                assistant_payload = {
                    "answer": (
                        "Sorry, something went wrong while processing your question. "
                        "Please try again."
                    ),
                    "citations": [],
                    "no_data": True,
                    "error": str(exc),
                }

        _render_assistant_message(assistant_payload, debug=debug)

    assistant_payload["role"] = "assistant"
    st.session_state["messages"].append(assistant_payload)


if __name__ == "__main__":
    main()
