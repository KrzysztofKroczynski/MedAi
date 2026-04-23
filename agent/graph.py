"""LangGraph graph definition and compilation for MedGraph AI agent."""

from langgraph.graph import StateGraph, END
from agent.state import AgentState
from agent.nodes.guardrail import guardrail_node, guardrail_router
from agent.nodes.router import router_node
from agent.nodes.executor import query_executor_node
from agent.nodes.decision import llm_decision_node, decision_router
from agent.nodes.citation import citation_node
from agent.nodes.summarizer import summarizer_node
from agent.memory import get_checkpointer


def build_graph():
    builder = StateGraph(AgentState)

    # Register processing nodes
    builder.add_node("guardrail", guardrail_node)
    builder.add_node("router", router_node)
    builder.add_node("executor", query_executor_node)
    builder.add_node("decision", llm_decision_node)
    builder.add_node("citation", citation_node)
    builder.add_node("summarizer", summarizer_node)

    # Rejection nodes — inline lambdas for simple message returns
    builder.add_node("reject_injection", lambda s: {
        "final_answer": (
            "This query cannot be processed. MedGraph AI is a pharmaceutical "
            "information tool and cannot respond to requests that attempt to "
            "modify its behaviour."
        )
    })
    builder.add_node("reject_offtopic", lambda s: {
        "final_answer": (
            "MedGraph AI only answers questions about medications, dosage, "
            "interactions, contraindications, and related pharmaceutical "
            "topics. Please rephrase your question or consult a pharmacist."
        )
    })

    # Entry point
    builder.set_entry_point("guardrail")

    # Edges
    builder.add_conditional_edges("guardrail", guardrail_router, {
        "router": "router",
        "reject_injection": "reject_injection",
        "reject_offtopic": "reject_offtopic"
    })

    builder.add_edge("router", "executor")
    builder.add_edge("executor", "decision")

    builder.add_conditional_edges("decision", decision_router, {
        "executor": "executor",   # NEED_MORE — loop back
        "citation": "citation"    # SUFFICIENT — proceed
    })

    builder.add_edge("citation", "summarizer")
    builder.add_edge("summarizer", END)
    builder.add_edge("reject_injection", END)
    builder.add_edge("reject_offtopic", END)

    checkpointer = get_checkpointer()
    return builder.compile(checkpointer=checkpointer)


# Module-level singleton — created once on first import
graph = build_graph()
