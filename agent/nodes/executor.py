"""Query executor node — runs all pending query plan items in parallel."""

import asyncio
from agent.state import AgentState, EvidenceItem
from agent.tools.cypher_tool import run_cypher_query
from agent.tools.web_tool import run_web_search

# Supplement with web when Neo4j content is below this length (characters).
# A single sparse record serialises to ~100-200 chars; rich results are 400+.
NEO4J_SUPPLEMENT_THRESHOLD = 300


async def query_executor_node(state: AgentState) -> dict:
    pending = [p for p in state["query_plan"] if p["status"] == "pending"]

    async def execute_one(item) -> list[EvidenceItem]:
        # Explicit web items skip Neo4j entirely
        if item["source"] == "web":
            return [await run_web_search(item)]

        neo4j_evidence = await asyncio.to_thread(run_cypher_query, item)

        if not neo4j_evidence["content"]:
            # Nothing in Neo4j — fall back to web only
            return [await run_web_search(item)]

        if len(neo4j_evidence["content"]) < NEO4J_SUPPLEMENT_THRESHOLD:
            # Thin Neo4j result — supplement with web
            web_evidence = await run_web_search(item)
            results = [neo4j_evidence]
            if web_evidence["content"]:
                results.append(web_evidence)
            return results

        return [neo4j_evidence]

    nested: list[list[EvidenceItem]] = await asyncio.gather(
        *[execute_one(item) for item in pending]
    )
    new_results = [ev for group in nested for ev in group]

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
