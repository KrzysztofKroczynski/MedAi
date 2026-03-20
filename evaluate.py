# Evaluation script for the 7 test scenarios defined in PDD.md (E-01 to E-07).
# For each scenario: sends the test question through the full RAG pipeline (retriever → context → qa).
# Checks:
#   - answer is non-empty and not a hallucination (no LLM memory fallback)
#   - answer contains at least one citation (source_file + page)
#   - "no data" scenarios (E-07) return the refusal message, not a fabricated answer
# Writes results to logs/evaluation_report.md with pass/fail per scenario.
