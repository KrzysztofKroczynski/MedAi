"""LLM decision node — determines whether to continue querying or proceed."""

import json
import os
from langchain_core.messages import HumanMessage
from shared.llm_client import get_client
from agent.state import AgentState, QueryPlan

_MAX_ITERATIONS = int(os.getenv("AGENT_MAX_ITERATIONS", "20"))
_llm = get_client(temperature=0)

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

  SUFFICIENT — choose this when ALL of the following hold:
    1. Every query_id in the plan has at least one EvidenceItem with
       substantive content (not just an empty list or placeholder).
    2. Neo4j results have non-empty node_names (real facts to cite), OR a web
       result with meaningful content covers the same intent.
    3. The evidence directly addresses the specific question asked — not just
       tangentially related. A user asking about drug interactions must have
       interaction evidence, not just general drug info.

  NEED_MORE — choose this when ANY of the following hold:
    1. A query_id has completely empty content (no Neo4j AND no web result)
       and a different query strategy (different entity spelling, web fallback)
       might succeed.
    2. The user's question explicitly names an entity that has not been queried
       at all yet (only entities the USER named — not drugs found in results).
    3. Evidence exists but is too thin to answer the specific question
       (e.g., interaction query returned general drug info with no interaction
       data, dosage query returned drug node with no dose details).

  Hard limits — always respect:
    - NEVER add a follow-up query for a drug or entity that only appeared
      inside a result snippet. Only follow up entities the USER explicitly
      named in their question.
    - NEVER re-query a (entity, intent) pair that already has substantive evidence.
    - NEVER issue more than 2 new query_ids per NEED_MORE round.
    - After 3 rounds of NEED_MORE with no improvement, choose SUFFICIENT and
      work with what you have.

If SUFFICIENT, respond with exactly:
DECISION: SUFFICIENT

If NEED_MORE, respond with:
DECISION: NEED_MORE
NEW_PLAN: [JSON array of new QueryPlan items]

The NEW_PLAN array must only include items for query_ids that still need work,
or new query_ids for follow-up entities. Use the same schema as the initial
query plan. All new items must have status "pending".
"""


def _strip_fences(text: str) -> str:
    """Strip markdown code fences from LLM JSON responses."""
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
    return text.strip()


async def llm_decision_node(state: AgentState) -> dict:
    # Runaway safety ceiling
    if state["iteration"] >= _MAX_ITERATIONS:
        return {"llm_decision": "SUFFICIENT", "next_query_plan": []}

    prompt = DECISION_PROMPT.format(
        user_message=state["messages"][-1].content,
        query_plan=json.dumps(state["query_plan"], indent=2),
        evidence_buffer=json.dumps(state["evidence_buffer"], indent=2)
    )

    result = await _llm.ainvoke([HumanMessage(content=prompt)])
    response = result.content.strip()

    if "DECISION: SUFFICIENT" in response:
        return {"llm_decision": "SUFFICIENT", "next_query_plan": []}

    # Parse NEED_MORE + new plan
    try:
        plan_start = response.index("NEW_PLAN:") + len("NEW_PLAN:")
        plan_json = _strip_fences(response[plan_start:].strip())
        new_plan: list[QueryPlan] = json.loads(plan_json)
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
