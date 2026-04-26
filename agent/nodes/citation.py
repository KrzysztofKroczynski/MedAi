"""Citation node — builds citations directly from evidence without LLM.

Selects node_names relevant to the user's question, fetches verbatim text
from the source PDF page, and formats attribution from source_citations.
"""

import os
import re
from pathlib import Path
from urllib.parse import urlparse

from agent.state import AgentState, CitationItem, EvidenceItem, QueryPlan, SourceLink

# Resolved at runtime so it works both locally and in Docker (/app/data/pdfs)
_PDFS_DIR = Path(os.getenv("PDFS_DIR", "data/pdfs"))


def _pdf_page_text(source_file: str, page_number: int) -> str:
    """Extract raw text from a specific PDF page (1-based)."""
    path = _PDFS_DIR / source_file
    if not path.exists():
        return ""
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        idx = max(0, page_number - 1)
        if idx >= len(reader.pages):
            return ""
        return reader.pages[idx].extract_text() or ""
    except Exception:
        return ""


def _relevant_snippet(page_text: str, keywords: list[str], max_chars: int = 400) -> str:
    """Return up to max_chars of page text centred on the first keyword hit."""
    text_lower = page_text.lower()
    for kw in keywords:
        pos = text_lower.find(kw.lower())
        if pos != -1:
            start = max(0, pos - 100)
            end = min(len(page_text), pos + max_chars)
            snippet = page_text[start:end].strip()
            # Clean up whitespace / newlines
            snippet = re.sub(r"\s+", " ", snippet)
            return snippet
    # Fallback: first max_chars chars of page
    return re.sub(r"\s+", " ", page_text[:max_chars]).strip()


def _relevant_node_names(
    node_names: list[str], user_message: str, entity: str
) -> list[str]:
    """Return the node_names most relevant to the user's question (up to 5).

    Keywords from the question are weighted higher than the drug entity name,
    so e.g. 'pregnant' scores above 'warfarin' when the question is about
    pregnancy — preventing the drug name from polluting the results.
    """
    entity_words = {w.lower() for w in re.split(r"\W+", entity) if len(w) > 2}
    all_words = {w for w in re.split(r"\W+", user_message.lower()) if len(w) > 3}
    question_words = all_words - entity_words  # non-entity terms carry more signal

    scored = []
    for name in node_names:
        name_lower = name.lower()
        q_score = sum(1 for w in question_words if w in name_lower)
        e_score = sum(0.1 for w in entity_words if w in name_lower)
        scored.append((q_score + e_score, name))

    scored.sort(key=lambda x: -x[0])
    best = [n for s, n in scored if s > 0]
    return (best[:5] if best else node_names[:5])


def _top_citations(
    source_citations: list[str], entity: str, max_links: int = 5
) -> list[str]:
    """Return up to max_links citations, preferring files that match the entity name.

    Preferred sources are capped at half the slots so non-matching sources
    (e.g. brand-name PDFs like Siofor for entity Metformin) always appear.
    """
    entity_lower = entity.lower().replace(" ", "_")
    preferred = [s for s in source_citations if entity_lower in s.lower()]
    others = [s for s in source_citations if s not in preferred]
    preferred_cap = max(1, max_links // 2)
    return (preferred[:preferred_cap] + others)[:max_links]


def _build_attribution(source_citations: list[str], entity: str) -> str:
    """Format up to 5 attribution strings; prefer files that match the entity name."""
    if not source_citations:
        return ""
    ordered = _top_citations(source_citations, entity, max_links=5)
    parts = []
    for s in ordered:
        if "|" in s:
            file, page = s.split("|", 1)
            parts.append(f"{file}, page {page}")
        else:
            parts.append(s)
    return " / ".join(parts)


def _source_links_from_citations(source_citations: list[str]) -> list[SourceLink]:
    """Build structured source links from raw citation strings."""
    links: list[SourceLink] = []
    seen: set[str] = set()

    for source in source_citations:
        if not source or source in seen:
            continue
        seen.add(source)

        if "|" in source:
            file_name, page_str = source.split("|", 1)
            page_number = None
            try:
                page_number = int(page_str)
            except ValueError:
                page_number = None

            label = f"{file_name}, page {page_number}" if page_number else file_name
            links.append(
                SourceLink(
                    label=label,
                    source_type="pdf",
                    file=file_name,
                    page=page_number,
                    url="",
                )
            )
            continue

        if source.startswith("http://") or source.startswith("https://"):
            parsed = urlparse(source)
            links.append(
                SourceLink(
                    label=parsed.netloc or source,
                    source_type="web",
                    file="",
                    page=None,
                    url=source,
                )
            )

    return links


def _cite_one(ev: EvidenceItem, plan_item: QueryPlan, user_message: str) -> CitationItem:
    """Build a single CitationItem from one evidence item."""
    if not ev["content"]:
        return CitationItem(
            query_id=ev["query_id"],
            intent=plan_item["intent"],
            answer_fragment=f"No data found for {plan_item['entity']} "
                            f"{plan_item['intent'].replace('_', ' ')}.",
            verbatim="",
            attribution="",
            source_links=[],
            source_type=ev["source_type"],
            found=False,
        )

    # --- Web result ---
    if ev["source_type"] == "web":
        snippet = re.sub(r"\s+", " ", ev["content"][:500]).strip()
        source_links = _source_links_from_citations(ev["source_citations"])
        attribution = ev["source_citations"][0] if ev["source_citations"] else "web search"
        return CitationItem(
            query_id=ev["query_id"],
            intent=plan_item["intent"],
            answer_fragment=snippet,
            verbatim=snippet[:200],
            attribution=attribution,
            source_links=source_links,
            source_type="web",
            found=True,
        )

    # --- Neo4j result ---
    if not ev["node_names"]:
        return CitationItem(
            query_id=ev["query_id"],
            intent=plan_item["intent"],
            answer_fragment=f"No data found for {plan_item['entity']} "
                            f"{plan_item['intent'].replace('_', ' ')}.",
            verbatim="",
            attribution="",
            source_links=[],
            source_type="neo4j",
            found=False,
        )

    # 1. Pick the most relevant node names
    relevant = _relevant_node_names(ev["node_names"], user_message, plan_item["entity"])
    verbatim = " / ".join(relevant)

    # 2. Build attribution (prefer entity-matching source files, cap at 5)
    top_cits = _top_citations(ev["source_citations"], plan_item["entity"], max_links=5)
    attribution = _build_attribution(ev["source_citations"], plan_item["entity"])
    source_links = _source_links_from_citations(top_cits)

    # 3. Fetch verbatim snippet from the primary source PDF
    pdf_snippet = ""
    if ev["source_citations"]:
        primary = ev["source_citations"][0]
        if "|" in primary:
            src_file, page_str = primary.split("|", 1)
            try:
                page_text = _pdf_page_text(src_file, int(page_str))
                if page_text:
                    keywords = [plan_item["entity"]] + relevant[:3]
                    pdf_snippet = _relevant_snippet(page_text, keywords)
            except (ValueError, Exception):
                pass

    answer_fragment = (
        pdf_snippet if pdf_snippet
        else f"{plan_item['entity']} {plan_item['intent'].replace('_', ' ')}: {verbatim}."
    )

    return CitationItem(
        query_id=ev["query_id"],
        intent=plan_item["intent"],
        answer_fragment=answer_fragment,
        verbatim=verbatim,
        attribution=attribution,
        source_links=source_links,
        source_type="neo4j",
        found=bool(verbatim and attribution),
    )


async def citation_node(state: AgentState) -> dict:
    user_message = state["messages"][-1].content
    # Use last plan entry per query_id (most recent wins after decision loops)
    plan_by_id = {p["query_id"]: p for p in state["query_plan"]}
    # Deduplicate evidence: keep the best (non-empty) item per query_id
    best_evidence: dict = {}
    for ev in state["evidence_buffer"]:
        qid = ev["query_id"]
        if qid not in best_evidence or (ev["content"] and not best_evidence[qid]["content"]):
            best_evidence[qid] = ev

    citations: list[CitationItem] = [
        _cite_one(ev, plan_by_id[ev["query_id"]], user_message)
        for ev in best_evidence.values()
        if ev["query_id"] in plan_by_id
    ]

    usable = [c for c in citations if c.get("found")]
    if not usable:
        return {
            "citations": [],
            "error": (
                "The available medication documents do not contain sufficient "
                "information to answer this question. Please consult a doctor "
                "or pharmacist."
            ),
        }

    return {"citations": citations, "error": None}
