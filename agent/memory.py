"""Session checkpointer for LangGraph persistence."""

from langgraph.checkpoint.memory import MemorySaver


def get_checkpointer():
    """Return an in-memory checkpointer for session persistence."""
    return MemorySaver()
