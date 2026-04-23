"""Streamlit chat UI for MedGraph AI — multi-agent backend."""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Any

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

    # Run async graph in a dedicated thread so it gets a clean event loop,
    # avoiding conflicts with Streamlit's own event loop.
    def _run():
        async def _ainvoke():
            return await graph.ainvoke(state, config=config)
        return asyncio.run(_ainvoke())

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(_run).result()

    answer = result.get("final_answer", "No answer generated.")
    citations = result.get("citations", [])

    return {
        "answer": answer,
        "citations": citations,
        "no_data": not answer,
    }


def _render_citations(citations: list[dict[str, Any]]) -> None:
    """Render structured CitationItem list returned by the agent."""
    if not citations:
        return
    for c in citations:
        if c.get("found"):
            st.markdown(
                f"**{c.get('intent', '')}** — {c.get('verbatim', '')}  \n"
                f"_{c.get('attribution', '')}_"
            )


def _render_assistant_message(payload: dict[str, Any]) -> None:
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


def main() -> None:
    st.set_page_config(page_title="MedGraph AI", page_icon="💊", layout="centered")
    st.title("💊 MedGraph AI")
    st.write("Ask medication questions in natural language.")

    if "session_id" not in st.session_state:
        st.session_state["session_id"] = str(uuid.uuid4())
    if "messages" not in st.session_state:
        st.session_state["messages"] = []

    for message in st.session_state["messages"]:
        role = message.get("role", "assistant")
        with st.chat_message(role):
            if role == "assistant":
                _render_assistant_message(message)
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

        _render_assistant_message(assistant_payload)

    assistant_payload["role"] = "assistant"
    st.session_state["messages"].append(assistant_payload)


if __name__ == "__main__":
    main()
