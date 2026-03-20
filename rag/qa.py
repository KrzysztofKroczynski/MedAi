# QA engine: generates the final answer from graph context using GPT-4o.
# Takes the user question and the assembled context dict from context.py.
# If context is empty: returns a fixed "no data" refusal message without calling the LLM.
# Otherwise: calls GPT-4o with QA_PROMPT (shared/prompts.py), passing the question and context text.
# The prompt strictly forbids the model from using knowledge outside the provided context.
# Appends citations (file + page) and a medical disclaimer to every response.
# Returns: { "answer": "...", "citations": [...], "disclaimer": "..." }
