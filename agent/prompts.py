# Agent-specific prompts live inline in their node files.
# This module re-exports them for discoverability.

from agent.nodes.guardrail import GUARDRAIL_SYSTEM
from agent.nodes.router import ROUTER_PROMPT
from agent.nodes.decision import DECISION_PROMPT
from agent.nodes.citation import CITATION_PROMPT
from agent.nodes.summarizer import SUMMARIZER_PROMPT, DISCLAIMER

__all__ = [
    "GUARDRAIL_SYSTEM",
    "ROUTER_PROMPT",
    "DECISION_PROMPT",
    "CITATION_PROMPT",
    "SUMMARIZER_PROMPT",
    "DISCLAIMER",
]
