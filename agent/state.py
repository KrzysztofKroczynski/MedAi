"""LangGraph state schema for MedGraph AI multi-agent pipeline."""

from typing import TypedDict, Annotated, Optional
from langgraph.graph.message import add_messages


class QueryPlan(TypedDict):
    query_id: str          # "A", "B", "C" — unique per decomposed intent
    intent: str            # "indication" | "contraindication" | "adverse_effect"
                           # | "dose" | "interaction" | "alternative" |
                           # "patient_group" | "general"
    entity: str            # primary drug or ingredient name
    secondary_entity: str  # second drug for interaction queries, else ""
    source: str            # "neo4j" | "web"
    status: str            # "pending" | "complete" | "no_result"


class EvidenceItem(TypedDict):
    query_id: str
    source_type: str       # "neo4j" | "web"
    content: str           # full raw result (list of dicts or web snippets)
    source_citations: list[str]   # ["source_file|page"] from relationship props
    node_names: list[str]  # names of matched nodes (for quote assembly)
    sufficient: bool       # set by LLM decision node


class SourceLink(TypedDict):
    label: str             # "filename.pdf, page 8" or URL host text
    source_type: str       # "pdf" | "web"
    file: str              # source PDF filename for pdf links
    page: Optional[int]    # 1-based page for pdf links
    url: str               # external URL for web links


class CitationItem(TypedDict):
    query_id: str
    intent: str
    answer_fragment: str   # the fact being cited
    verbatim: str          # exact node name or relationship property value
    attribution: str       # "filename, page N" or URL
    source_links: list[SourceLink]
    source_type: str       # "neo4j" | "web"
    found: bool


class AgentState(TypedDict):
    # Conversation history (append-only via add_messages reducer)
    messages: Annotated[list, add_messages]
    session_id: str

    # Session context — persisted across turns via checkpointer
    session_context: dict  # keys: current_drug, current_indication, turn_count

    # Guardrail result
    guardrail_label: str   # "MEDICAL" | "OFF_TOPIC" | "INJECTION"

    # Query planning
    query_plan: list[QueryPlan]

    # Iteration state
    iteration: int
    evidence_buffer: list[EvidenceItem]

    # Decision
    llm_decision: str          # "SUFFICIENT" | "NEED_MORE"
    next_query_plan: list[QueryPlan]

    # Output
    citations: list[CitationItem]
    final_answer: str
    error: Optional[str]
