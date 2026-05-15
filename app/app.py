"""Streamlit chat UI for MedGraph AI."""

from __future__ import annotations

import concurrent.futures
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

_HERE = Path(os.path.abspath(__file__)).parent
_ROOT = _HERE.parent
for _p in (_ROOT, _HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from pipeline import run_agent_query, run_pdf_ingestion  # noqa: E402

logger = logging.getLogger(__name__)

PROJECT_ROOT = _ROOT
DATA_PDFS_DIR = PROJECT_ROOT / "data" / "pdfs"
STATIC_PDFS_DIR = _HERE / "static" / "pdfs"

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


# ---------------------------------------------------------------------------
# Static PDF sync
# ---------------------------------------------------------------------------

def _sync_static_pdfs() -> None:
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
    base = f"/app/static/pdfs/{quote(file_name, safe='')}"
    return f"{base}#page={page_number}" if page_number else base


# ---------------------------------------------------------------------------
# Agent trace rendering
# ---------------------------------------------------------------------------

def _format_node_trace(node_name: str, updates: dict) -> dict:
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
    if not trace:
        container.info("No trace available — run a query first.")
        return

    for step in trace:
        node = step.get("node", "unknown")
        icon, label = _NODE_META.get(node, ("⚙️", node))
        summary = step.get("summary", "")

        with container.expander(f"{icon} **{label}** — {summary}", expanded=False):
            if node == "guardrail":
                st.write(f"**Label:** `{step.get('label', '')}`")

            elif node == "router":
                for item in step.get("query_plan", []):
                    se = item.get("secondary_entity", "")
                    entity_str = item["entity"] + (f" ↔ {se}" if se else "")
                    st.markdown(
                        f"- `{item['query_id']}` **{item['intent']}** — "
                        f"{entity_str} _(source: {item['source']})_"
                    )

            elif node == "executor":
                for ev in step.get("evidence", []):
                    src_icon = "🗄️" if ev["source"] == "neo4j" else "🌐"
                    nodes_str = ", ".join(ev["nodes"][:5]) or "—"
                    st.markdown(
                        f"{src_icon} `{ev['query_id']}` · **{ev['source']}** · "
                        f"{ev['content_chars']} chars · nodes: _{nodes_str}_"
                    )
                    for cit in ev["citations"][:3]:
                        st.caption(f"  📄 {cit}")

            elif node == "decision":
                st.write(f"**Decision:** `{step.get('decision')}`")
                st.write(f"**Iteration:** {step.get('iteration')}")
                for q in step.get("next_queries", []):
                    st.markdown(f"- `{q['query_id']}` {q['intent']} / {q['entity']}")

            elif node == "citation":
                for c in step.get("citations", []):
                    found_icon = "✅" if c.get("found") else "❌"
                    st.markdown(
                        f"{found_icon} `{c.get('query_id')}` **{c.get('intent')}** — "
                        f"{c.get('verbatim', '')[:120]}"
                    )
                    if c.get("attribution"):
                        st.caption(f"  ↳ {c['attribution']}")

            elif node == "summarizer":
                st.write("**Session context after this turn:**")
                st.json(step.get("session_context", {}))
                st.write("**Answer preview:**")
                st.text(step.get("answer_preview", ""))

            elif node in ("reject_injection", "reject_offtopic"):
                st.write(step.get("reason", ""))

            else:
                st.json(step.get("raw", {}))


# ---------------------------------------------------------------------------
# Citation rendering
# ---------------------------------------------------------------------------

def _render_citations(citations: list[dict[str, Any]]) -> None:
    for c in citations:
        if not c.get("found"):
            continue
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


# ---------------------------------------------------------------------------
# Assistant message rendering
# ---------------------------------------------------------------------------

def _render_assistant_message(payload: dict[str, Any], debug: bool = False) -> None:
    answer = str(payload.get("answer", "")).strip()
    citations = payload.get("citations", [])

    if payload.get("no_data") and not answer:
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
# Memory / debug panel
# ---------------------------------------------------------------------------

def _get_agent_memory(session_id: str) -> dict[str, Any] | None:
    try:
        from agent.graph import graph
        config = {"configurable": {"thread_id": session_id}}
        snapshot = graph.get_state(config)
        if snapshot is None:
            return None
        values = snapshot.values
        messages = values.get("messages", [])
        serialized = [
            {"role": getattr(m, "type", type(m).__name__), "content": m.content}
            for m in messages
        ]
        return {
            "session_id": session_id,
            "session_context": values.get("session_context", {}),
            "messages": serialized,
            "turn_count": values.get("session_context", {}).get("turn_count", 0),
        }
    except Exception as exc:
        return {"error": str(exc)}


def _render_memory_panel(session_id: str) -> None:
    st.sidebar.title("🧠 Memory Inspector")
    st.sidebar.caption(f"Session: `{session_id}`")

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

    trace = st.session_state.get("agent_trace", [])
    st.sidebar.subheader(f"Last Run — Agent Trace ({len(trace)} steps)")
    _render_agent_trace(trace, st.sidebar)


# ---------------------------------------------------------------------------
# PDF upload sidebar
# ---------------------------------------------------------------------------

def _render_upload_sidebar() -> None:
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


# ---------------------------------------------------------------------------
# Ingestion panel (UI only — calls pipeline.run_pdf_ingestion)
# ---------------------------------------------------------------------------

def _render_ingestion_panel() -> None:
    pdf_path: Path = st.session_state["ingestion_pdf_path"]
    filename: str = st.session_state["ingestion_filename"]

    st.title("💊 MedGraph AI — Ingesting PDF")
    st.caption(f"File: `{filename}`")

    if not st.session_state.get("ingestion_done"):
        overall = st.progress(0, text="Starting…")

        with st.status("Running ingestion pipeline…", expanded=True) as pipeline_status:
            st.write("⏳ Loading, chunking, extracting entities, writing to Neo4j…")
            st.caption("Extraction runs concurrently — this may take several minutes.")

            extraction_bar = st.progress(0.0, text="Waiting for chunks…")
            progress: dict[str, int] = {"completed": 0, "total": 0}

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(run_pdf_ingestion, pdf_path, progress)
                while not future.done():
                    total = progress["total"]
                    done = progress["completed"]
                    if total > 0:
                        overall.progress(
                            int(15 + 60 * done / total),
                            text=f"Extracting… {done}/{total} chunks",
                        )
                        extraction_bar.progress(done / total, text=f"{done} / {total} chunks")
                    time.sleep(0.4)
                result = future.result()

            extraction_bar.progress(1.0, text=f"{result['extractions']} / {result['chunks']} chunks")
            overall.progress(100, text="Done!")

            # Surface errors
            if result["error"] == "no_pages":
                pipeline_status.update(label="❌ Failed — no pages loaded", state="error")
                st.error("No pages could be read from the PDF. Check the file and try again.")
                return
            if result["error"] == "no_chunks":
                pipeline_status.update(label="❌ Failed — no chunks generated", state="error")
                st.error("Text chunking produced no output.")
                return

            # Stage summaries
            st.write(f"✅ **Pages loaded:** {result['pages']}")
            st.write(f"✅ **Chunks:** {result['chunks']} (800 tokens, 150 overlap)")

            entity_count = sum(len(names) for names in result["entity_types"].values())
            rel_count = result["relations"]
            st.write(
                f"✅ **Extracted:** {result['extractions']} records — "
                f"~{entity_count} entities, {rel_count} relations"
            )

            if rel_count == 0 and entity_count > 0:
                st.warning(
                    "⚠️ **0 relations extracted.** Entities were found but no relationships between "
                    "them. Only nodes linked by at least one relation are written to Neo4j. "
                    "This often happens with non-English PDFs or image-only documents."
                )

            if result["entity_types"]:
                with st.expander("🔬 Extracted entities by type", expanded=True):
                    for etype, names in sorted(result["entity_types"].items()):
                        names_sorted = sorted(names)
                        preview = ", ".join(f"`{n}`" for n in names_sorted[:30])
                        overflow = f" _+{len(names_sorted) - 30} more_" if len(names_sorted) > 30 else ""
                        st.markdown(f"**{etype}** ({len(names_sorted)}): {preview}{overflow}")

            st.write(
                f"✅ **Cache:** {result['cache_total']} total records in "
                "`data/processed/extractions.json`"
            )
            st.write(
                f"✅ **Neo4j:** {result['nodes']} nodes, {result['relations']} relations written"
            )

            if result["failed"]:
                st.warning(f"{result['failed']} records failed to write — check the logs.")

            if result["nodes"] == 0 and result["extractions"] > 0:
                st.error(
                    "⚠️ **0 nodes written to Neo4j.** The graph builder only writes nodes that "
                    "appear as endpoints of at least one relation. "
                    + ("No valid relations were found — check that the PDF language and content "
                       "are supported by the extraction prompt." if rel_count == 0 else
                       "All extracted relations may have failed schema validation — check the logs.")
                )
            elif result["neo4j_breakdown"]:
                breakdown = ", ".join(
                    f"{r['lbls'][-1]}: {r['cnt']}" for r in result["neo4j_breakdown"] if r["lbls"]
                )
                st.caption(f"Neo4j verification — nodes from `{filename}`: {breakdown}")

            nodes_ok = result["nodes"] > 0
            pipeline_status.update(
                label=f"{'✅' if nodes_ok else '⚠️'} Ingestion complete — {filename}",
                state="complete" if nodes_ok else "error",
            )

        _sync_static_pdfs()
        st.session_state["ingestion_done"] = True
        st.session_state["ingestion_result"] = result

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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    _sync_static_pdfs()

    st.set_page_config(page_title="MedGraph AI", page_icon="💊", layout="centered")

    if "session_id" not in st.session_state:
        st.session_state["session_id"] = str(uuid.uuid4())
    if "messages" not in st.session_state:
        st.session_state["messages"] = []

    if st.session_state.get("ingestion_active"):
        _render_upload_sidebar()
        _render_ingestion_panel()
        return

    _render_upload_sidebar()

    st.title("💊 MedGraph AI")
    st.write("Ask medication questions in natural language.")

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
                pipeline_result = run_agent_query(
                    user_question, st.session_state["session_id"]
                )
            except Exception as exc:
                logger.exception("Agent pipeline failed")
                pipeline_result = {
                    "answer": "Sorry, something went wrong. Please try again.",
                    "citations": [],
                    "no_data": True,
                    "trace": [],
                    "error": str(exc),
                }

        # Format raw trace for display and store in session state
        st.session_state["agent_trace"] = [
            _format_node_trace(item["node_name"], item["updates"])
            for item in pipeline_result.get("trace", [])
        ]

        assistant_payload = {k: v for k, v in pipeline_result.items() if k != "trace"}
        _render_assistant_message(assistant_payload, debug=debug)

    assistant_payload["role"] = "assistant"
    st.session_state["messages"].append(assistant_payload)


if __name__ == "__main__":
    main()
