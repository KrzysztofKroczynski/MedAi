"""Router node — extracts intents and produces a structured query plan."""

import json
from langchain_core.messages import HumanMessage
from shared.llm_client import get_client
from agent.state import AgentState, QueryPlan

ROUTER_PROMPT = """
You are the query planner for MedGraph AI, a pharmaceutical information
assistant. Your job is to analyse the user's question and session context,
then produce a structured query plan.

Session context (resolved from prior conversation turns):
  current_drug:        {current_drug}
  current_indication:  {current_indication}

User question: {user_message}

Produce a JSON array. Each item represents one distinct information need.

Each item must have:
  query_id          Short uppercase letter: "A", "B", "C", etc.
  intent            One of: indication, contraindication, adverse_effect,
                    dose, interaction, alternative, patient_group, general
  entity            Primary drug name — MUST be the INN (International
                    Nonproprietary Name) generic name. The knowledge graph
                    indexes drugs by INN only, so brand names will NOT match.
                    If the user mentions a brand name, translate it to INN
                    before setting this field.
                    Examples: Siofor → Metformin, Nurofen → Ibuprofen,
                    Tylenol → Acetaminophen, Xanax → Alprazolam.
                    Resolve "it", "this drug", "the medication" using
                    current_drug from context.
  secondary_entity  Second drug name for interaction queries. Empty string
                    otherwise.
  source            "neo4j" if likely in PIL/SmPC database.
                    "web" if a supplement, brand-only drug, or very new
                    compound unlikely to be in the indexed documents.
  status            Always "pending" for new items.

Rules:
  - One item per distinct question. If the user asks two things, produce two
    items.
  - Never produce more than 5 items per turn.
  - If the entity cannot be resolved from the question or context, set it to
    "unknown" — the executor will handle this case.
  - Respond with only the JSON array. No explanation, no markdown.

Examples:

Input: "What are the side effects of ibuprofen and can I take it with warfarin?"
Output:
[
  {{"query_id": "A", "intent": "adverse_effect", "entity": "Ibuprofen",
    "secondary_entity": "", "source": "neo4j", "status": "pending"}},
  {{"query_id": "B", "intent": "interaction", "entity": "Ibuprofen",
    "secondary_entity": "Warfarin", "source": "neo4j", "status": "pending"}}
]

Input: "What is the dose for children?" (current_drug = "Paracetamol")
Output:
[
  {{"query_id": "A", "intent": "dose", "entity": "Paracetamol",
    "secondary_entity": "", "source": "neo4j", "status": "pending"}}
]
"""


async def router_node(state: AgentState) -> dict:
    llm = get_client(temperature=0)
    ctx = state.get("session_context", {})

    prompt = ROUTER_PROMPT.format(
        current_drug=ctx.get("current_drug", "unknown"),
        current_indication=ctx.get("current_indication", "unknown"),
        user_message=state["messages"][-1].content
    )

    result = await llm.ainvoke([HumanMessage(content=prompt)])

    try:
        raw = result.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.startswith("json"):
                raw = raw[4:]
        plan: list[QueryPlan] = json.loads(raw.strip())
    except (json.JSONDecodeError, ValueError):
        # Fallback: single general query with entity from context
        plan = [{
            "query_id": "A",
            "intent": "general",
            "entity": ctx.get("current_drug", "unknown"),
            "secondary_entity": "",
            "source": "neo4j",
            "status": "pending"
        }]

    return {
        "query_plan": plan,
        "evidence_buffer": [],
        "iteration": 0,
        "llm_decision": "",
        "next_query_plan": [],
        "citations": [],
        "error": None
    }
