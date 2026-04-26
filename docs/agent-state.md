# Agent State Schema

All data flowing through the LangGraph pipeline lives in `AgentState` — a single TypedDict passed into and returned from every node.

**File:** `agent/state.py`

---

## AgentState

```python
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]  # append-only conversation history
    session_id: str
    session_context: dict                    # current_drug, current_indication, turn_count
    guardrail_label: str                     # "MEDICAL" | "OFF_TOPIC" | "INJECTION"
    query_plan: list[QueryPlan]
    iteration: int
    evidence_buffer: list[EvidenceItem]
    llm_decision: str                        # "SUFFICIENT" | "NEED_MORE"
    next_query_plan: list[QueryPlan]
    citations: list[CitationItem]
    final_answer: str
    error: Optional[str]
```

### Field notes

| Field | Set by | Notes |
|-------|--------|-------|
| `messages` | app + summarizer | `add_messages` reducer appends; never overwrites |
| `session_context` | summarizer | Persisted across turns via `MemorySaver`; `current_drug` used by router for pronoun resolution ("it", "this drug") |
| `guardrail_label` | guardrail | Controls routing after guardrail node |
| `query_plan` | router, decision | Accumulates across loops; items go `pending → complete` |
| `iteration` | executor | Incremented each executor pass; compared against `AGENT_MAX_ITERATIONS` |
| `evidence_buffer` | executor | Accumulates across loops; citation node deduplicates by `query_id` |
| `llm_decision` | decision | `"SUFFICIENT"` → go to citation; `"NEED_MORE"` → loop back to executor |
| `next_query_plan` | decision | Additional items added when `NEED_MORE` |
| `citations` | citation | List of `CitationItem`; only `found=True` items used by summarizer |
| `error` | citation | Set if no usable citations found; summarizer returns error + disclaimer without LLM call |

---

## QueryPlan

Represents one distinct information need decomposed from the user's question.

```python
class QueryPlan(TypedDict):
    query_id: str          # "A", "B", "C" — unique per intent
    intent: str            # "indication" | "contraindication" | "adverse_effect"
                           # | "dose" | "interaction" | "alternative"
                           # | "patient_group" | "general"
    entity: str            # primary drug name (INN generic)
    secondary_entity: str  # second drug for interaction queries; else ""
    source: str            # "neo4j" | "web" (router hint; executor always tries neo4j first)
    status: str            # "pending" | "complete" | "no_result"
```

**Example** — question "What are the side effects of ibuprofen and can I take it with warfarin?":

```json
[
  {"query_id": "A", "intent": "adverse_effect", "entity": "Ibuprofen",
   "secondary_entity": "", "source": "neo4j", "status": "pending"},
  {"query_id": "B", "intent": "interaction", "entity": "Ibuprofen",
   "secondary_entity": "Warfarin", "source": "neo4j", "status": "pending"}
]
```

---

## EvidenceItem

Raw evidence returned by the executor for one `QueryPlan` item.

```python
class EvidenceItem(TypedDict):
    query_id: str
    source_type: str            # "neo4j" | "web"
    content: str                # raw result (stringified record list or web snippet)
    source_citations: list[str] # ["filename|page"] from relationship props; ["DuckDuckGo web search"] for web
    node_names: list[str]       # matched node names used for keyword scoring in citation node
    sufficient: bool            # unused; decision node evaluates sufficiency directly
```

---

## SourceLink

Structured source reference embedded in each `CitationItem`. Used by the UI to render clickable PDF page links or web URLs.

```python
class SourceLink(TypedDict):
    label: str             # "filename.pdf, page 8" or URL host text
    source_type: str       # "pdf" | "web"
    file: str              # source PDF filename (pdf links only)
    page: Optional[int]    # 1-based page number (pdf links only)
    url: str               # external URL (web links only)
```

---

## CitationItem

Structured citation produced by the citation node for one `EvidenceItem`.

```python
class CitationItem(TypedDict):
    query_id: str
    intent: str
    answer_fragment: str         # verbatim PDF page snippet (or web content snippet)
    verbatim: str                # selected node names joined by " / "
    attribution: str             # "filename, page N" or URL (plain text for the summarizer prompt)
    source_links: list[SourceLink]  # structured links for UI rendering
    source_type: str             # "neo4j" | "web"
    found: bool                  # False → summarizer emits "not found" for this intent
```

Only `CitationItem`s with `found=True` carry evidence into the summarizer prompt.
