# Agent Pipeline — High-Level Overview

## Purpose

Answer natural language pharmaceutical questions using a stateful LangGraph multi-agent pipeline. The pipeline replaces the legacy single-pass RAG approach with iterative, parallel evidence gathering, deterministic citation building, and grounded answer synthesis.

## Pipeline Flow

```
user input
  │
  ▼
[guardrail]       Classify: MEDICAL / OFF_TOPIC / INJECTION (single LLM call)
  │
  ├─ OFF_TOPIC  ──► reject_offtopic  ──► END
  ├─ INJECTION  ──► reject_injection ──► END
  │
  ▼
[router]          Decompose question into QueryPlan items (intent + entity per fact needed)
  │
  ▼
[executor]        Run all pending items in parallel:
  │                 → try Neo4j Cypher first
  │                 → fall back to DuckDuckGo web search if empty
  ▼
[decision]        LLM evaluates evidence: SUFFICIENT or NEED_MORE
  │
  ├─ NEED_MORE  ──► [executor]  (loop — hard cap: AGENT_MAX_ITERATIONS)
  │
  ▼
[citation]        Deterministic: score node_names, fetch verbatim PDF page text
  │
  ▼
[summarizer]      Synthesize grounded answer with inline [Source: …] citations
  │
  ▼
  END             final_answer + citations returned to app
```

## Key Properties

| Property | Detail |
|----------|--------|
| **Async** | All nodes are `async def`; `asyncio.gather` runs executor items in parallel |
| **Stateful** | `AgentState` TypedDict flows through every node; `MemorySaver` persists session context across turns |
| **Iterative** | Decision node can loop the executor up to `AGENT_MAX_ITERATIONS` times |
| **Grounded** | Citation node fetches verbatim text from actual PDF pages via `pypdf` — no LLM hallucination in citations |
| **Safe** | Guardrail rejects off-topic and injection attempts before any graph query is executed |
| **Injection-safe** | All Cypher queries use `$entity` / `$secondary_entity` parameters — user input never interpolated into query text |

## Module Map

```
agent/
  graph.py          Build + compile the LangGraph StateGraph
  state.py          AgentState, QueryPlan, EvidenceItem, CitationItem TypedDicts
  memory.py         MemorySaver checkpointer (session context per thread_id)
  nodes/
    guardrail.py    Input classifier
    router.py       Query plan decomposer
    executor.py     Parallel Cypher + web search runner
    decision.py     SUFFICIENT / NEED_MORE evaluator
    citation.py     Deterministic citation builder
    summarizer.py   Final answer synthesizer
  tools/
    cypher_tool.py  8 parameterised Cypher templates
    web_tool.py     DuckDuckGo fallback search
```

## Detailed Documentation

- [State Schema](./agent-state.md)
- [Nodes](./agent-nodes.md)
- [Tools: Cypher + Web Search](./agent-tools.md)
