"""Web search fallback tool for MedGraph AI agent — DuckDuckGo only."""

import asyncio

from agent.state import QueryPlan, EvidenceItem

from langchain_community.tools import DuckDuckGoSearchRun

_search = DuckDuckGoSearchRun()


async def run_web_search(item: QueryPlan) -> EvidenceItem:
    """Run a pharmaceutical-focused web search for the given QueryPlan item."""
    parts = [item["entity"], item["intent"].replace("_", " ")]
    if item.get("secondary_entity"):
        parts.append(item["secondary_entity"])
    parts.append("patient information leaflet")
    query = " ".join(parts)

    try:
        results = await asyncio.to_thread(_search.invoke, query)
    except Exception:
        results = ""

    if not results:
        return EvidenceItem(
            query_id=item["query_id"],
            source_type="web",
            content="",
            source_citations=[],
            node_names=[],
            sufficient=False,
        )

    return EvidenceItem(
        query_id=item["query_id"],
        source_type="web",
        content=str(results),
        source_citations=["DuckDuckGo web search"],
        node_names=[],
        sufficient=False,
    )
