# Streamlit chat interface for MedGraph AI.
# Renders a chat window where the user types medication questions in natural language.
# On submit: calls rag/retriever.py → rag/context.py → rag/qa.py pipeline.
# Displays the answer, source citations (file + page), and medical disclaimer.
# If qa.py returns a "no data" response, shows a styled warning instead of a normal answer.
# Maintains conversation history in Streamlit session state for multi-turn context.
# Does NOT allow the user to override the safety disclaimer.
