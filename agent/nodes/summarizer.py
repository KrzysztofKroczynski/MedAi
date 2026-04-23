"""Summarizer node — synthesizes the final answer with inline citations."""

import json
from langchain_core.messages import HumanMessage, AIMessage
from shared.llm_client import get_client
from agent.state import AgentState

SUMMARIZER_PROMPT = """
You are the answer synthesizer for MedGraph AI, a pharmaceutical information
assistant used by healthcare professionals and patients.

Answer the user's question using ONLY the citations provided below.
Do not use your training knowledge to add any facts not present in the
citations. Do not invent doses, interactions, or contraindications.

User question: {user_message}

Citations (structured, pre-verified):
{citations}

Each citation contains:
  - source_type: "neo4j" (extracted from a licensed PIL/SmPC PDF) or "web"
  - answer_fragment: verbatim text extracted from the source document
  - verbatim: the specific facts most relevant to the question
  - attribution: the source document and page

Source priority rules — follow these strictly:
  1. Neo4j citations (source_type "neo4j") come from licensed pharmaceutical
     documents. Always prefer them over web citations for the same query_id.
  2. Use a web citation only when no neo4j citation covers the same fact, or
     to add a detail that the neo4j citation does not contain.
  3. Never let a web citation override or contradict a neo4j citation.
  4. If neo4j and web citations disagree, state the neo4j finding and note
     that web sources differ.

Format rules:
  - Write 2-4 sentences directly answering the question.
  - Ground every claim in the answer_fragment or verbatim field.
  - After each claim add [Source: <attribution>] inline.
  - If found is false: "Information about [intent] was not found in the
    indexed documents."
  - End with this disclaimer on its own line:
    "⚠️ This information is provided for reference only. Always consult a
     doctor or pharmacist before making any medication decision."
  - Do not speculate or add facts beyond what the citations contain.
  - Do not repeat the full verbatim list — use it only to ground your answer.
"""

DISCLAIMER = (
    "\n\n⚠️ This information is provided for reference only. Always consult "
    "a doctor or pharmacist before making any medication decision."
)


async def summarizer_node(state: AgentState) -> dict:
    # If citation node set an error, return it directly without LLM call
    if state.get("error"):
        answer = state["error"] + DISCLAIMER
        return {
            "final_answer": answer,
            "messages": [AIMessage(content=answer)]
        }

    llm = get_client(temperature=0)
    prompt = SUMMARIZER_PROMPT.format(
        user_message=state["messages"][-1].content,
        citations=json.dumps(state["citations"], indent=2)
    )

    result = await llm.ainvoke([HumanMessage(content=prompt)])
    answer = result.content

    # Ensure disclaimer is present even if LLM omitted it
    if "consult a doctor or pharmacist" not in answer.lower():
        answer += DISCLAIMER

    # Update session context with the primary drug from this turn
    primary_entity = None
    for item in state.get("query_plan", []):
        if item.get("entity") and item["entity"] != "unknown":
            primary_entity = item["entity"]
            break

    updated_ctx = dict(state.get("session_context", {}))
    if primary_entity:
        updated_ctx["current_drug"] = primary_entity
    updated_ctx["turn_count"] = updated_ctx.get("turn_count", 0) + 1

    return {
        "final_answer": answer,
        "session_context": updated_ctx,
        "messages": [AIMessage(content=answer)]
    }
