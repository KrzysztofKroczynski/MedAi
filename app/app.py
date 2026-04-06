# Streamlit chat interface for MedGraph AI.
# Renders a chat window where the user types medication questions in natural language.
# On submit: calls rag/retriever.py → rag/context.py → rag/qa.py pipeline.
# Displays the answer, source citations (file + page), and medical disclaimer.
# If qa.py returns a "no data" response, shows a styled warning instead of a normal answer.
# Maintains conversation history in Streamlit session state for multi-turn context.
# Does NOT allow the user to override the safety disclaimer.
"""Streamlit chat UI for MedGraph AI."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Callable

import streamlit as st


logger = logging.getLogger(__name__)

DEFAULT_DISCLAIMER = (
    "Medical disclaimer: This assistant is for informational purposes only and "
    "does not replace professional medical advice, diagnosis, or treatment."
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _resolve_callable(module: Any, candidates: list[str]) -> Callable:
    """Resolve first available callable from candidate names."""
    for name in candidates:
        fn = getattr(module, name, None)
        if callable(fn):
            return fn
    raise AttributeError(
        f"No callable found in {module.__name__}. Tried: {', '.join(candidates)}"
    )


def _run_rag_pipeline(question: str) -> dict[str, Any]:
    """Run retriever -> context assembler -> QA pipeline."""
    try:
        from rag import context as context_module
        from rag import qa as qa_module
        from rag import retriever as retriever_module
    except Exception as exc:
        logger.warning("RAG modules unavailable, using UI-only fallback: %s", exc)
        return {
            "answer": (
                "RAG backend is not available yet, so I can’t query medication knowledge yet. "
                "UI mode is active and this will work once rag modules are implemented."
            ),
            "citations": [],
            "disclaimer": DEFAULT_DISCLAIMER,
            "no_data": True,
        }

    retrieve_fn = _resolve_callable(
        retriever_module,
        ["retrieve", "retrieve_context", "run_retriever", "get_retrieval_rows"],
    )
    assemble_context_fn = _resolve_callable(
        context_module,
        ["assemble_context", "build_context", "format_context", "rows_to_context"],
    )
    qa_fn = _resolve_callable(
        qa_module,
        ["answer_question", "run_qa", "generate_answer", "qa"],
    )

    rows = retrieve_fn(question)
    context_bundle = assemble_context_fn(rows)
    qa_result = qa_fn(question, context_bundle)

    if not isinstance(qa_result, dict):
        qa_result = {"answer": str(qa_result)}

    answer_text = str(qa_result.get("answer", "")).strip()
    citations = qa_result.get("citations", context_bundle.get("citations", []))
    disclaimer = str(qa_result.get("disclaimer") or DEFAULT_DISCLAIMER)

    no_data_hint = str(answer_text).lower()
    is_no_data = (
        bool(qa_result.get("no_data"))
        or "no data" in no_data_hint
        or "insufficient context" in no_data_hint
        or "cannot answer" in no_data_hint
    )

    return {
        "answer": answer_text or "No answer generated.",
        "citations": citations if isinstance(citations, list) else [],
        "disclaimer": disclaimer,
        "no_data": is_no_data,
    }


def _render_citations(citations: list[dict[str, Any]]) -> None:
    if not citations:
        return

    st.markdown("**Sources:**")
    for citation in citations:
        file_name = citation.get("file") or citation.get("source_file") or "Unknown file"
        page = citation.get("page") or citation.get("page_number") or "?"
        st.markdown(f"- `{file_name}` (page {page})")


def _render_assistant_message(payload: dict[str, Any]) -> None:
    answer = str(payload.get("answer", "")).strip()
    citations = payload.get("citations", [])
    disclaimer = str(payload.get("disclaimer") or DEFAULT_DISCLAIMER)
    is_no_data = bool(payload.get("no_data"))

    if is_no_data:
        st.warning(answer or "No data available to answer this question.")
    else:
        st.markdown(answer or "No answer generated.")

    _render_citations(citations if isinstance(citations, list) else [])

    st.markdown("---")
    st.caption(disclaimer)


def main() -> None:
    st.set_page_config(page_title="MedGraph AI", page_icon="💊", layout="centered")
    st.title("💊 MedGraph AI")
    st.write("Ask medication questions in natural language.")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for message in st.session_state.messages:
        role = message.get("role", "assistant")
        with st.chat_message(role):
            if role == "assistant":
                _render_assistant_message(message)
            else:
                st.markdown(message.get("content", ""))

    user_question = st.chat_input("E.g., Can Ibuprofen interact with Warfarin?")
    if not user_question:
        return

    st.session_state.messages.append({"role": "user", "content": user_question})
    with st.chat_message("user"):
        st.markdown(user_question)

    with st.chat_message("assistant"):
        with st.spinner("Searching graph and generating answer..."):
            try:
                assistant_payload = _run_rag_pipeline(user_question)
            except Exception as exc:
                logger.exception("RAG pipeline failed")
                assistant_payload = {
                    "role": "assistant",
                    "answer": (
                        "Sorry, something went wrong while processing your question. "
                        "Please try again."
                    ),
                    "citations": [],
                    "disclaimer": DEFAULT_DISCLAIMER,
                    "no_data": True,
                    "error": str(exc),
                }

        _render_assistant_message(assistant_payload)

    assistant_payload["role"] = "assistant"
    st.session_state.messages.append(assistant_payload)


if __name__ == "__main__":
    main()
