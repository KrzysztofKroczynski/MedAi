"""LLM decision node — determines whether to continue querying or proceed."""

import json
import os
from langchain_core.messages import HumanMessage
from shared.llm_client import get_client
from agent.state import AgentState, QueryPlan

_MAX_ITERATIONS = int(os.getenv("AGENT_MAX_ITERATIONS", "20"))

DECISION_PROMPT = """
You are the reasoning engine for MedGraph AI, a pharmaceutical information
assistant.

Review the accumulated evidence and decide whether you have enough to produce
a complete, citation-grounded answer to the user's question.

User question:
{user_message}

Query plan (all items, all rounds):
{query_plan}

Evidence accumulated so far:
{evidence_buffer}

Evaluate using these criteria:

  SUFFICIENT — stop querying when ALL are true:
    1. Every query_id has at least one EvidenceItem with non-empty content.
    2. For Neo4j results: node_names is non-empty (there are facts to cite).
    3. For web results: content is non-empty and source_citations is non-empty.
    4. No result referenced an entity that the question also requires but that
       has not yet been queried (e.g. a result mentions ActiveIngredient Y and
       the user asked about Y's interactions — Y must be queried too).
    5. Additional queries would not realistically improve the answer.

  NEED_MORE — continue querying when ANY are true:
    1. One or more query_ids have empty content (no results found yet).
    2. A prior result (Neo4j OR web) mentions a drug name or clinical entity
       that is directly relevant to answering the user's question, and that
       entity has not yet been queried in Neo4j — add a new Neo4j query for it.
    3. A Neo4j result was thin (only 1-2 facts) and a web search for the same
       intent has not yet been attempted — add a web query for the same item.
    4. A web result mentions a drug or active ingredient that is likely in the
       Neo4j database (a known pharmaceutical, not a brand or supplement) and
       has not been queried there yet — add a Neo4j query to cross-reference.
    5. The source was web and the snippet is too short (<100 chars) to be
       useful — retry with a more specific query.

  Anti-patterns — never do these:
    - Do not re-query a query_id that already has good evidence.
    - Do not query the same (entity, intent) pair more than twice total.
    - Do not add new query_ids for tangential facts unrelated to the user's
      question (only follow up entities that directly answer what was asked).
    - Do not manufacture sufficiency — if evidence is weak, say NEED_MORE.

If SUFFICIENT, respond with exactly:
DECISION: SUFFICIENT

If NEED_MORE, respond with:
DECISION: NEED_MORE
NEW_PLAN: [JSON array of new QueryPlan items]

The NEW_PLAN array must only include items for query_ids that still need work,
or new query_ids for follow-up entities. Use the same schema as the initial
query plan. All new items must have status "pending".
"""


async def llm_decision_node(state: AgentState) -> dict:
    # Runaway safety ceiling
    if state["iteration"] >= _MAX_ITERATIONS:
        return {"llm_decision": "SUFFICIENT", "next_query_plan": []}

    llm = get_client(temperature=0)
    prompt = DECISION_PROMPT.format(
        user_message=state["messages"][-1].content,
        query_plan=json.dumps(state["query_plan"], indent=2),
        evidence_buffer=json.dumps(state["evidence_buffer"], indent=2)
    )

    result = await llm.ainvoke([HumanMessage(content=prompt)])
    response = result.content.strip()

    if "DECISION: SUFFICIENT" in response:
        return {"llm_decision": "SUFFICIENT", "next_query_plan": []}

    # Parse NEED_MORE + new plan
    try:
        plan_start = response.index("NEW_PLAN:") + len("NEW_PLAN:")
        plan_json = response[plan_start:].strip()
        if plan_json.startswith("```"):
            plan_json = plan_json.split("```", 2)[1]
            if plan_json.startswith("json"):
                plan_json = plan_json[4:]
        new_plan: list[QueryPlan] = json.loads(plan_json.strip())
        for item in new_plan:
            item["status"] = "pending"
    except (ValueError, json.JSONDecodeError):
        # Cannot parse — treat as sufficient rather than loop
        return {"llm_decision": "SUFFICIENT", "next_query_plan": []}

    updated_plan = state["query_plan"] + new_plan

    return {
        "llm_decision": "NEED_MORE",
        "next_query_plan": new_plan,
        "query_plan": updated_plan
    }


def decision_router(state: AgentState) -> str:
    if state["iteration"] >= _MAX_ITERATIONS or state["llm_decision"] == "SUFFICIENT":
        return "citation"
    return "executor"
