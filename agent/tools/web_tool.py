"""Web search fallback tool for MedGraph AI agent — DuckDuckGo only."""

import asyncio

from agent.state import QueryPlan, EvidenceItem

from langchain_community.tools import DuckDuckGoSearchRun

_search = DuckDuckGoSearchRun()


_PATIENT_INTENTS = {"contraindication", "patient_group"}

# Maximum number of words taken from patient_profile to keep query focused.
_PROFILE_WORD_LIMIT = 8


async def run_web_search(item: QueryPlan, patient_profile: str = "") -> EvidenceItem:
    """Run a pharmaceutical-focused web search for the given QueryPlan item."""
    if item["intent"] == "multi_interaction" and item.get("drug_list"):
        parts = item["drug_list"] + ["drug interactions"]
    else:
        parts = [item["entity"], item["intent"].replace("_", " ")]
        if item.get("secondary_entity"):
            parts.append(item["secondary_entity"])

        # For patient-specific intents, add profile keywords so the search
        # targets the patient's actual conditions rather than generic leaflets.
        if item["intent"] in _PATIENT_INTENTS and patient_profile:
            profile_words = patient_profile.split()[:_PROFILE_WORD_LIMIT]
            parts.extend(profile_words)
        else:
            parts.append("patient information leaflet")

    query = " ".join(parts)

    try:
        results = await asyncio.to_thread(_search.invoke, query)
    except Exception:
        results = ""

    if not results:
        return EvidenceItem(
            query_id=item["query_id"],
            source_type="web",
            content="",
            source_citations=[],
            node_names=[],
            sufficient=False,
        )

    return EvidenceItem(
        query_id=item["query_id"],
        source_type="web",
        content=str(results),
        source_citations=["DuckDuckGo web search"],
        node_names=[],
        sufficient=False,
    )
