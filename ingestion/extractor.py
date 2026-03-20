# Entity and relation extractor for medication text chunks.
# Calls the LLM using ENTITY_EXTRACTION_PROMPT from shared/prompts.py.
# Gets the client and model from shared/llm_client.py (MODEL).
# For each chunk, sends the text to the LLM and parses the returned JSON.
# Expected JSON structure:
#   {
#     "entities": [{"type": "Drug", "name": "Ibuprofen"}, ...],
#     "relations": [{"from": "Ibuprofen", "rel": "INTERACTS_WITH", "to": "Warfarin"}, ...]
#   }
# Should handle LLM errors and malformed JSON gracefully (log and skip the chunk).
# Returns a list of extraction result dicts, each paired with the chunk's source metadata.
