"""Router node — extracts intents and produces a structured query plan."""

import json
from langchain_core.messages import HumanMessage
from shared.llm_client import get_client
from agent.state import AgentState, QueryPlan

_llm = get_client(temperature=0)

ROUTER_PROMPT = """
You are the query planner for MedGraph AI, a pharmaceutical information
assistant. Your job is to analyse the user's question and session context,
then produce a structured query plan.

Session context (resolved from prior conversation turns):
  current_drug:    {current_drug}
  current_indication: {current_indication}
  patient_profile: {patient_profile}

User question: {user_message}

Produce a JSON array. Each item represents one distinct information need.

Each item must have:
  query_id          Short uppercase letter: "A", "B", "C", etc.
  intent            One of: indication, contraindication, adverse_effect,
                    dose, interaction, multi_interaction, alternative,
                    patient_group, general
  entity            Primary drug name — MUST be the INN (International
                    Nonproprietary Name) generic name. The knowledge graph
                    indexes drugs by INN only, so brand names will NOT match.
                    If the user mentions a brand name, translate it to INN
                    before setting this field.
                    Examples: Siofor → Metformin, Nurofen → Ibuprofen,
                    Tylenol → Acetaminophen, Xanax → Alprazolam.
                    Resolve "it", "this drug", "the medication" using
                    current_drug from context.
                    For multi_interaction, set entity to the first drug.
  secondary_entity  Second drug name for interaction (two-drug) queries.
                    Empty string for all other intents including
                    multi_interaction.
  drug_list         Non-empty list of all drug INNs ONLY for
                    multi_interaction. Omit (or set to []) for every other
                    intent.
  source            "neo4j" if likely in PIL/SmPC database.
                    "web" if a supplement, brand-only drug, or very new
                    compound unlikely to be in the indexed documents.
  status            Always "pending" for new items.

Rules:
  - One item per distinct question. If the user asks two things, produce two
    items.
  - Never produce more than 5 items per turn EXCEPT when using
    multi_interaction (one item covers all pairs regardless of drug count).
  - If the entity cannot be resolved from the question or context, set it to
    "unknown" — the executor will handle this case.
  - Respond with only the JSON array. No explanation, no markdown.
  - MULTI-DRUG INTERACTION RULE: if the user asks about interactions among 3
    or more drugs at once, produce exactly ONE item with intent
    multi_interaction. Set entity to the first drug INN. Set drug_list to the
    complete list of all drug INNs mentioned. Set secondary_entity to "".
    Do NOT produce individual interaction pairs — multi_interaction finds all
    pairs in a single graph query.
  - PATIENT CONTEXT RULE: if the user is providing patient information ("I am
    X", "I have Y", "patient is Z") without naming a new drug, this is a
    follow-up about current_drug. Query for contraindications and patient_group
    warnings for current_drug. Do NOT query about the medical conditions
    themselves — always query the DRUG.

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

Input: "I am 23 and pregnant" (current_drug = "Ibuprofen")
Output:
[
  {{"query_id": "A", "intent": "contraindication", "entity": "Ibuprofen",
    "secondary_entity": "", "source": "neo4j", "status": "pending"}},
  {{"query_id": "B", "intent": "patient_group", "entity": "Ibuprofen",
    "secondary_entity": "", "source": "neo4j", "status": "pending"}}
]

Input: "Is it safe to take Aspirin, Warfarin, Ibuprofen, Metformin, and Lisinopril together?"
Output:
[
  {{"query_id": "A", "intent": "multi_interaction",
    "entity": "Aspirin", "secondary_entity": "",
    "drug_list": ["Aspirin", "Warfarin", "Ibuprofen", "Metformin", "Lisinopril"],
    "source": "neo4j", "status": "pending"}}
]
"""


def _strip_fences(text: str) -> str:
    """Strip markdown code fences from LLM JSON responses."""
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
    return text.strip()


async def router_node(state: AgentState) -> dict:
    ctx = state.get("session_context", {})

    prompt = ROUTER_PROMPT.format(
        current_drug=ctx.get("current_drug", "unknown"),
        current_indication=ctx.get("current_indication", "unknown"),
        patient_profile=ctx.get("patient_profile", "unknown"),
        user_message=state["messages"][-1].content
    )

    result = await _llm.ainvoke([HumanMessage(content=prompt)])

    try:
        plan: list[QueryPlan] = json.loads(_strip_fences(result.content.strip()))
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
