# Agent Nodes

All nodes are `async def` functions. They receive `AgentState` and return a partial state dict that LangGraph merges back.

---

## guardrail — `agent/nodes/guardrail.py`

**Purpose:** Classify input before any graph query runs.

**LLM calls:** 1 (temperature=0)

**Output labels:**

| Label | Meaning | Next node |
|-------|---------|-----------|
| `MEDICAL` | Genuine pharmaceutical question | `router` |
| `OFF_TOPIC` | Unrelated to medication | `reject_offtopic` → END |
| `INJECTION` | Prompt manipulation attempt | `reject_injection` → END |

**Fallback:** Any unexpected label is treated as `MEDICAL`.

**Rejection messages** (inline lambdas in `graph.py`):
- `reject_offtopic`: "MedGraph AI only answers questions about medications…"
- `reject_injection`: "This query cannot be processed…"

---

## router — `agent/nodes/router.py`

**Purpose:** Decompose the user question into a structured `QueryPlan` list.

**LLM calls:** 1 (temperature=0)

**Session context used:**
- `current_drug` — resolves pronouns ("it", "this drug", "the medication")
- `current_indication` — resolves indication references across turns

**Brand → INN translation:** The prompt explicitly instructs the LLM to translate brand names to their INN (International Nonproprietary Name) generic name before setting `entity`, because the graph indexes drugs by INN only. Examples baked into the prompt: Siofor → Metformin, Nurofen → Ibuprofen, Tylenol → Acetaminophen, Xanax → Alprazolam.

**Output:** Up to 5 `QueryPlan` items, one per distinct information need.

**Intent types:**

| Intent | Cypher template used |
|--------|---------------------|
| `indication` | `INDICATED_FOR` traversal |
| `contraindication` | `CONTRAINDICATED_IN` traversal |
| `adverse_effect` | `WARNS_FOR` traversal |
| `dose` | `HAS_DOSE` traversal |
| `interaction` | `INTERACTS_WITH` traversal (bidirectional) |
| `alternative` | `ALTERNATIVE_FOR` traversal (bidirectional) |
| `patient_group` | `CONTRAINDICATED_IN` / `WARNS_FOR` / `HAS_DOSE` on `PatientGroup` nodes |
| `general` | Multi-hop overview: indication + adverse effects + contraindications |

**Fallback:** If LLM returns invalid JSON, produces a single `general` query for `current_drug`.

**State resets on each call:** `evidence_buffer`, `iteration`, `llm_decision`, `next_query_plan`, `citations`, `error` — ensures a clean slate for the new question.

---

## executor — `agent/nodes/executor.py`

**Purpose:** Execute all `pending` QueryPlan items in parallel.

**LLM calls:** 0

**Execution logic per item:**
1. If `source == "web"` → skip Neo4j entirely, run `run_web_search(item)` only
2. Otherwise run `run_cypher_query(item)` via `asyncio.to_thread` (sync Neo4j driver):
   - If Neo4j returns **empty** content → fall back to `run_web_search(item)` only
   - If Neo4j result is **thin** (< `NEO4J_SUPPLEMENT_THRESHOLD` = 300 chars) → keep Neo4j result **and** append `run_web_search(item)` result
   - If Neo4j result is rich (≥ 300 chars) → use Neo4j result only
3. Append result(s) to `evidence_buffer`; mark item `complete`

**Parallelism:** All pending items run concurrently via `asyncio.gather`.

**Iteration counter:** Incremented by 1 each executor pass.

---

## decision — `agent/nodes/decision.py`

**Purpose:** Evaluate accumulated evidence and decide whether to loop or proceed.

**LLM calls:** 1 (temperature=0)

**Hard cap:** If `iteration >= AGENT_MAX_ITERATIONS` (default 20), returns `SUFFICIENT` immediately without LLM call.

**Outputs:**

| Decision | Effect |
|----------|--------|
| `SUFFICIENT` | Routes to `citation` node |
| `NEED_MORE` | Appends new `QueryPlan` items; routes back to `executor` |

**Fallback:** If `NEED_MORE` response cannot be parsed, treats as `SUFFICIENT` to prevent infinite loops.

**Anti-patterns enforced by prompt:**
- Never re-query a `query_id` that already has good evidence
- Never query the same (entity, intent) pair more than twice
- Never add new query_ids for facts outside the original question

---

## citation — `agent/nodes/citation.py`

**Purpose:** Build structured `CitationItem` list from evidence. Fully deterministic — no LLM call.

**LLM calls:** 0

**Steps per evidence item:**

1. **Deduplication** — keep best (non-empty) `EvidenceItem` per `query_id`
2. **Node scoring** — `_relevant_node_names()` ranks graph node names by keyword overlap with the user question; entity name words weighted at 0.1× (question-specific words score 1 point each; entity name words score 0.1 each) to avoid drug-name pollution swamping clinical-term matches
3. **PDF fetch** — `_pdf_page_text()` reads the primary source PDF page via `pypdf`; `_relevant_snippet()` extracts up to 400 chars centred on the first keyword hit
4. **Attribution** — `_build_attribution()` formats up to 5 source files; preferred files (name contains the entity) are capped at half the slots so non-matching sources (e.g. a brand-name PDF like `Siofor` for entity `Metformin`) always appear

**Web evidence:** Uses `ev["content"]` directly as `answer_fragment` (first 500 chars); `source_citations[0]` as attribution.

**Empty result handling:** If all `CitationItem`s have `found=False`, sets `state["error"]` and returns empty citations list. Summarizer then returns the error message + disclaimer without an LLM call.

---

## summarizer — `agent/nodes/summarizer.py`

**Purpose:** Synthesize a grounded natural language answer from citations.

**LLM calls:** 1 (temperature=0) — skipped entirely if `state["error"]` is set.

**Format rules enforced by prompt:**
- 2–4 sentences directly answering the question
- Every claim grounded in `answer_fragment` or `verbatim` field
- Inline `[Source: <attribution>]` after each claim
- `found=False` items → "Information about [intent] was not found in the indexed documents."
- Disclaimer appended if LLM omits it: "⚠️ This information is provided for reference only…"

**Session context update:** After synthesis, `current_drug` is set to the first resolved entity from the query plan; `turn_count` is incremented.

**Output:** `final_answer` (str) + `AIMessage` appended to `messages`.
