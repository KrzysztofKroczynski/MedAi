"""Web search fallback tool for MedGraph AI agent.

Tries Tavily first (requires TAVILY_API_KEY); falls back to DuckDuckGo.
"""

from agent.state import QueryPlan, EvidenceItem

# Attempt Tavily (new package first, then legacy); fall back to DuckDuckGo.
try:
    from langchain_tavily import TavilySearch
    _search = TavilySearch(max_results=5)
    _search_mode = "tavily"
except Exception:
    try:
        from langchain_community.tools.tavily_search import TavilySearchResults
        _search = TavilySearchResults(max_results=5)
        _search_mode = "tavily"
    except Exception:
        try:
            from langchain_community.tools import DuckDuckGoSearchRun
            _search = DuckDuckGoSearchRun()
            _search_mode = "duckduckgo"
        except Exception:
            _search = None
            _search_mode = "none"


async def run_web_search(item: QueryPlan) -> EvidenceItem:
    """Run a pharmaceutical-focused web search for the given QueryPlan item."""
    if _search is None:
        return EvidenceItem(
            query_id=item["query_id"],
            source_type="web",
            content="",
            source_citations=[],
            node_names=[],
            sufficient=False
        )

    parts = [item["entity"], item["intent"].replace("_", " ")]
    if item.get("secondary_entity"):
        parts.append(item["secondary_entity"])
    parts.append("patient information leaflet")
    query = " ".join(parts)

    try:
        results = await _search.ainvoke(query)
    except Exception:
        # DuckDuckGoSearchRun may not support ainvoke — try sync via thread
        import asyncio
        try:
            results = await asyncio.to_thread(_search.invoke, query)
        except Exception:
            results = []

    if not results:
        return EvidenceItem(
            query_id=item["query_id"],
            source_type="web",
            content="",
            source_citations=[],
            node_names=[],
            sufficient=False
        )

    if _search_mode == "tavily" and isinstance(results, list):
        snippets = [r.get("content", "") for r in results[:3]]
        urls = [r.get("url", "") for r in results[:3]]
    else:
        # DuckDuckGo returns a plain string — use a generic attribution
        snippets = [str(results)]
        urls = ["DuckDuckGo web search"]

    return EvidenceItem(
        query_id=item["query_id"],
        source_type="web",
        content="\n\n".join(snippets),
        source_citations=urls,
        node_names=[],
        sufficient=False
    )
