"""LangGraph state schema for MedGraph AI multi-agent pipeline."""

from typing import TypedDict, Annotated, Optional
from langgraph.graph.message import add_messages


def _merge_ctx(a: dict | None, b: dict | None) -> dict:
    """Merge reducer for session_context — deep-merges so nodes can do partial
    updates without wiping keys they didn't touch."""
    return {**(a or {}), **(b or {})}


class _QueryPlanRequired(TypedDict):
    query_id: str          # "A", "B", "C" — unique per decomposed intent
    intent: str            # "indication" | "contraindication" | "adverse_effect"
                           # | "dose" | "interaction" | "multi_interaction" |
                           # "alternative" | "patient_group" | "general"
    entity: str            # primary drug INN (first drug for multi_interaction)
    secondary_entity: str  # second drug for interaction queries, else ""
    source: str            # "neo4j" | "web"
    status: str            # "pending" | "complete" | "no_result"


class QueryPlan(_QueryPlanRequired, total=False):
    drug_list: list[str]   # all drug INNs for multi_interaction; omit otherwise


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

    # Session context — persisted across turns via checkpointer; uses merge
    # reducer so individual nodes can return partial updates safely.
    session_context: Annotated[dict, _merge_ctx]

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
