# GraphRAG retriever: translates a user question into a Cypher query and fetches graph context.
# Step 1 — use CYPHER_GENERATION_PROMPT (shared/prompts.py) with GPT-4o to produce a
#   Cypher READ query from the user's natural language question and the graph schema.
# Step 2 — execute the generated Cypher against Neo4j via shared/neo4j_client.py.
# Step 3 — return the raw result rows plus any source metadata attached to the matched nodes.
# Should validate that the generated Cypher is a READ-only query before executing.
# On empty result, returns an empty list (not an error) so the QA layer can issue a "no data" response.
