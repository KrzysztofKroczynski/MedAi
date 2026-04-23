"""Query executor node — runs all pending query plan items in parallel."""

import asyncio
from agent.state import AgentState, EvidenceItem
from agent.tools.cypher_tool import run_cypher_query
from agent.tools.web_tool import run_web_search


async def query_executor_node(state: AgentState) -> dict:
    pending = [p for p in state["query_plan"] if p["status"] == "pending"]

    async def execute_one(item):
        # Try Neo4j first regardless of source assignment
        evidence = await asyncio.to_thread(run_cypher_query, item)

        # Fall back to web if Neo4j returned nothing or source is explicitly web
        if not evidence["content"] or item["source"] == "web":
            evidence = await run_web_search(item)

        return evidence

    new_results: list[EvidenceItem] = await asyncio.gather(
        *[execute_one(item) for item in pending]
    )

    updated_buffer = state["evidence_buffer"] + list(new_results)

    # Mark executed items complete
    pending_ids = {item["query_id"] for item in pending}
    updated_plan = [
        {**item, "status": "complete"} if item["query_id"] in pending_ids
        else item
        for item in state["query_plan"]
    ]

    return {
        "evidence_buffer": updated_buffer,
        "query_plan": updated_plan,
        "iteration": state["iteration"] + 1
    }
