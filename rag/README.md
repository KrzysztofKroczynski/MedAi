# rag — GraphRAG module

Purpose
-------
The rag package implements a small, testable Graph-based Retrieval-Augmented Generation (GraphRAG) component for MedGraph AI. It provides:
- An LLM-driven entity/relationship extractor for document chunks.
- Mapping of extracted objects into a canonical Neo4j graph schema.
- An idempotent ingestion pipeline that writes nodes/relationships and records ingestion metadata.
- A GraphRAG query engine that retrieves supporting evidence from the graph and generates citation-first answers (honest refusal when no evidence).

Design goals
------------
- Citation-first answers: every factual sentence in generated answers must reference source ids from the indexed documents.
- Honest refusal: do not hallucinate; return a standardized refusal when evidence is insufficient.
- Idempotent ingestion: stable ids prevent duplicate nodes/relationships across repeated ingestions.
- Testability: LLM and Neo4j interactions are adapter-based and easily mocked in unit tests.

Contents
--------
- models.py — dataclasses for Node/Relationship/Citation/ExtractionResult/QueryResult.
- schema.py — canonical labels/relationship types and normalization helpers.
- neo4j_client.py — lightweight idempotent Neo4j client wrapper and helpers.
- prompts.py — centralized prompts and builders (extraction, answer, refusal guardrails).
- entity_extractor.py — adapter that drives the LLM for structured extraction and maps outputs to models.
- ingest.py — ingestion pipeline that extracts and upserts graph data, recording metadata.
- graph_rag.py — retrieval (keyword + neighbor expansion), context assembly, LLM answer generation with citations.
- utils.py — small helpers (env loader, logging setup, retry/backoff, JSON parsing, snippets).
- tests/ — unit tests with mocks for LLM and Neo4j.

Environment variables
---------------------
- OPENAI_API_KEY — OpenAI API key used by shared LLM adapter if used.
- NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD — Neo4j connection.
- Optional: LLM_PROVIDER, MODEL as configured by shared/llm_client.py.

Quickstart (developer)
----------------------
1. Create a Python venv and install dev deps (example):
   python -m venv .venv
   . .venv/bin/activate
   pip install -r requirements.txt
   pip install -r requirements-dev.txt

2. Run unit tests:
   .venv/bin/python -m pytest -q

3. Ingest sample chunks (pseudocode):
   from rag import Neo4jClient, extractor_from_callable, ingest_from_list
   client = Neo4jClient()  # configure via env vars or args
   llm = lambda prompt: ...  # inject your LLM callable or a mock
   extractor = extractor_from_callable(llm)
   report = ingest_from_list(chunks, extractor, client)

4. Query the graph:
   from rag import grag_from_callable
   rag = grag_from_callable(client, llm)
   result = rag.answer_query("Can ibuprofen and warfarin be used together?")
   print(result.answer)

How to check if everything works
-------------------------------
1. Run the test suite: .venv/bin/python -m pytest -q — tests mock external systems and validate behavior.
2. Linting and static checks: run your project's linters (optional).
3. Manual smoke test:
   - Start Neo4j (or use a test double).
   - Create a small chunk list and a mock LLM callable that returns deterministic JSON for extraction.
   - Run ingest.ingest_chunks and verify Neo4j contains expected nodes/relationships.
   - Run GraphRAG.answer_query with a mock LLM that respects citation markers and ensure the returned QueryResult contains citations and provenance.

Possible improvements
---------------------
- Better LLM adapters: accept LangChain/ChatOpenAI instances directly (already supported in shared/llm_client.py but could be wired into EntityExtractor/GraphRAG as optional adapters).
- Robust JSON parsing: implement heuristics to recover JSON embedded in text outputs for the extractor.
- Schema extensions: add more node/relationship types and validation tests in schema.py.
- CLI utilities: provide a CLI entrypoint for bulk ingestion and basic query commands.
- More granular tests: add integration tests that spin up a test Neo4j container (docker-compose) for real ingestion verification.

Security and safety
-------------------
- Do not bypass the refusal logic for medical queries.
- Avoid logging raw user inputs in production logs. Keep ingestion/query traces for auditing but sanitize sensitive data.
- Validate and sanitize any parsed JSON from the LLM before writing to the graph.

Contributing
------------
- Implement features behind interfaces so tests can mock external systems.
- Keep prompts centralized in prompts.py and add tests that assert citation presence in outputs.
- Run tests before submitting changes.

License
-------
Repository license applies.
