"""Agent and ingestion pipeline logic — no Streamlit imports."""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

_HERE = Path(os.path.abspath(__file__)).parent
_ROOT = _HERE.parent
for _p in (_ROOT, _HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

logger = logging.getLogger(__name__)

PROJECT_ROOT = _ROOT


# ---------------------------------------------------------------------------
# Agent pipeline
# ---------------------------------------------------------------------------

def run_agent_query(user_input: str, session_id: str) -> dict[str, Any]:
    """Invoke the LangGraph pipeline. Returns answer, citations, no_data, raw trace."""
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
            "trace": [],
        }

    state = {
        "messages": [HumanMessage(content=user_input)],
        "session_id": session_id,
        "session_context": {},
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

    raw_trace: list[dict] = []
    final_answer = ""
    citations: list = []

    def _run() -> None:
        nonlocal final_answer, citations

        async def _astream() -> None:
            nonlocal final_answer, citations
            async for chunk in graph.astream(state, config=config, stream_mode="updates"):
                for node_name, updates in chunk.items():
                    raw_trace.append({"node_name": node_name, "updates": updates})
                    if "final_answer" in updates and updates["final_answer"]:
                        final_answer = updates["final_answer"]
                    if "citations" in updates:
                        citations = updates["citations"]

        asyncio.run(_astream())

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(_run).result()

    return {
        "answer": final_answer or "No answer generated.",
        "citations": citations,
        "no_data": not final_answer,
        "trace": raw_trace,
    }


# ---------------------------------------------------------------------------
# Ingestion pipeline
# ---------------------------------------------------------------------------

def _append_to_extraction_cache(new_extractions: list[dict]) -> int:
    """Merge new extractions into cache. Returns total record count."""
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


def run_pdf_ingestion(
    pdf_path: Path,
    progress: dict[str, int] | None = None,
) -> dict[str, Any]:
    """
    Run the full PDF ingestion pipeline (load → chunk → extract → cache → Neo4j).

    progress: optional mutable dict with keys ``completed`` and ``total``.
              Pipeline sets ``total`` after chunking and increments ``completed``
              per extracted chunk so the caller can drive a live progress bar.

    Returns a result dict with keys:
        pages, chunks, extractions, entity_types, cache_total,
        nodes, relations, failed, neo4j_breakdown, error
    """
    result: dict[str, Any] = {
        "pages": 0,
        "chunks": 0,
        "extractions": 0,
        "entity_types": {},
        "cache_total": 0,
        "nodes": 0,
        "relations": 0,
        "failed": 0,
        "neo4j_breakdown": [],
        "error": None,
    }

    filename = pdf_path.name

    # Stage 1: Load
    from ingestion.loader import load_single_pdf
    docs = load_single_pdf(pdf_path)
    result["pages"] = len(docs)
    if not docs:
        result["error"] = "no_pages"
        return result

    # Stage 2: Chunk
    from ingestion.chunker import chunk_documents
    chunks = chunk_documents(docs)
    result["chunks"] = len(chunks)
    if not chunks:
        result["error"] = "no_chunks"
        return result

    if progress is not None:
        progress["total"] = len(chunks)

    # Stage 3: Extract
    from ingestion.extractor import extract_from_chunks

    def _on_chunk_done() -> None:
        if progress is not None:
            progress["completed"] += 1

    extractions = extract_from_chunks(chunks, on_chunk_done=_on_chunk_done)
    result["extractions"] = len(extractions)

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
    result["entity_types"] = entity_types

    # Stage 4: Cache
    result["cache_total"] = _append_to_extraction_cache(extractions)

    # Stage 5: Neo4j
    from graph.graph_builder import write_extractions
    from graph.schema import apply as apply_schema

    apply_schema()
    stats = write_extractions(extractions)
    result["nodes"] = stats.get("nodes", 0)
    result["relations"] = stats.get("relations", 0)
    result["failed"] = stats.get("failed", 0)

    if result["nodes"] > 0:
        try:
            from shared.neo4j_client import get_driver
            driver = get_driver()
            with driver.session() as sess:
                rows = sess.run(
                    "MATCH (n) WHERE n.source_file = $f "
                    "RETURN labels(n) AS lbls, count(n) AS cnt ORDER BY cnt DESC",
                    f=filename,
                ).data()
            result["neo4j_breakdown"] = rows
        except Exception as exc:
            logger.warning("Neo4j verification failed: %s", exc)

    return result
