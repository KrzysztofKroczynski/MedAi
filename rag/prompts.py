"""Centralized prompt templates and builders for GraphRAG.

Provides:
- extraction prompt template for entity/relationship extraction from a text chunk
- answer prompt template enforcing citation-first answers and honest refusal
- small builders that assemble prompts with context/citations
"""

from typing import List, Dict, Optional

EXTRACTION_PROMPT_TEMPLATE = (
    "You are an information extraction assistant.\n"
    "Extract medical entities, relationships and citations from the provided text chunk.\n"
    "Return a JSON object with keys: nodes (list), relationships (list), citations (list).\n"
    "Each node should have: 'type' (e.g. Drug), 'text' (surface form), 'properties' (optional dict).\n"
    "Each relationship should have: 'type' (e.g. INTERACTS_WITH), 'source' (node_text), 'target' (node_text), 'properties'.\n"
    "Citations should include: source_id, doc_id (if available), page (optional), excerpt (optional).\n"
    "Do NOT hallucinate: only include entities/relations you can infer from the chunk.\n"
    "Output only valid JSON.\n"
    "---\n"
    "CHUNK:\n{chunk}\n"
)


RAG_ANSWER_SYSTEM_INSTRUCTIONS = (
    "You are a medical assistant that must answer user questions strictly based on provided evidence snippets.\n"
    "Rules:\n"
    "1) Citation-first: every factual sentence must include an inline citation marker referencing one or more source_ids from the provided citations (format: [CITATION:source_id]).\n"
    "2) If the evidence is insufficient to answer, return the standardized refusal message exactly as provided. Do not attempt to answer.\n"
    "3) Be concise and avoid hallucination. When multiple sources support a claim, include all relevant citation markers.\n"
)


RAG_ANSWER_PROMPT_TEMPLATE = (
    "{system_instructions}\n"
    "User question: {question}\n"
    "Available evidence snippets and citations:\n{evidence}\n"
    "Citations metadata:\n{citations}\n"
    "Answer the question with citations inline using the format [CITATION:source_id].\n"
    "If you must refuse, output only the refusal string:\n{refusal}\n"
)


REFUSAL_MESSAGE = (
    "I cannot find sufficient evidence in the indexed documents to answer this question. "
    "Please consult a healthcare professional."
)


def build_extraction_prompt(chunk: str, doc_id: Optional[str] = None, chunk_id: Optional[str] = None) -> str:
    """Return a filled extraction prompt for the LLM."""
    header = EXTRACTION_PROMPT_TEMPLATE
    meta = []
    if doc_id:
        meta.append(f"doc_id: {doc_id}")
    if chunk_id:
        meta.append(f"chunk_id: {chunk_id}")
    meta_str = "\n".join(meta)
    if meta_str:
        header = header + "\n" + meta_str + "\n"
    return header.format(chunk=chunk)


def build_answer_prompt(question: str, evidence_snippets: List[Dict[str, str]], citations: List[Dict[str, str]]) -> str:
    """Assemble the RAG answer prompt from question, snippets and citation metadata.

    evidence_snippets: list of dicts with keys: source_id, text (snippet)
    citations: list of dicts with citation metadata (source_id, doc_id, page, excerpt)
    """
    # format evidence
    ev_lines = []
    for i, s in enumerate(evidence_snippets, start=1):
        sid = s.get("source_id") or s.get("id") or f"S{i}"
        text = s.get("text") or s.get("snippet") or ""
        ev_lines.append(f"[{sid}] {text}")
    evidence_block = "\n".join(ev_lines) if ev_lines else "(no evidence provided)"

    # format citations metadata
    cit_lines = []
    for c in citations:
        cid = c.get("source_id") or c.get("id")
        doc = c.get("doc_id")
        page = c.get("page")
        excerpt = c.get("excerpt")
        parts = [f"source_id={cid}"]
        if doc:
            parts.append(f"doc_id={doc}")
        if page:
            parts.append(f"page={page}")
        if excerpt:
            parts.append(f"excerpt={excerpt}")
        cit_lines.append(
            "; ".join(parts)
        )
    citations_block = "\n".join(cit_lines) if cit_lines else "(no citations)"

    return RAG_ANSWER_PROMPT_TEMPLATE.format(
        system_instructions=RAG_ANSWER_SYSTEM_INSTRUCTIONS,
        question=question,
        evidence=evidence_block,
        citations=citations_block,
        refusal=REFUSAL_MESSAGE,
    )


# small helper to build an inline citation token for answer generation via prompts
def inline_citation_token(source_id: str) -> str:
    return f"[CITATION:{source_id}]"


