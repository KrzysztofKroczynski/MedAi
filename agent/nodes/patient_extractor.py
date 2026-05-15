"""Patient profile extractor node — extracts and persists patient context."""

from langchain_core.messages import HumanMessage
from shared.llm_client import get_client
from agent.state import AgentState

_llm = get_client(temperature=0)

PATIENT_EXTRACTOR_PROMPT = """
You are extracting patient profile information for a pharmaceutical assistant.

Current patient profile (from prior turns):
{existing_profile}

Latest user message:
{user_message}

CRITICAL RULE: Only extract information the user explicitly states about
THEMSELVES using first-person language ("I am", "I have", "I take", "I'm",
"I was diagnosed", "my condition", "patient is", etc.).

Do NOT extract:
  - Drugs or foods the user is merely ASKING about ("can I take X?",
    "is X safe?", "what about X?") — these are query subjects, not patient facts.
  - General questions, hypothetical scenarios, or third-party information.

Extract ONLY explicit self-disclosures such as:
  - Age, sex, body weight
  - Pregnancy or breastfeeding status
  - Diagnosed medical conditions ("I have diabetes", "I am hypertensive")
  - Medications the patient states they personally take ("I take metformin")
  - Allergies ("I am allergic to penicillin")
  - Organ impairment ("I have chronic kidney disease")
  - Special patient group ("I am 8 months pregnant", "I am elderly")

Merge extracted facts with the existing profile. New information takes
precedence when it conflicts with old.

If the message contains no qualifying patient information, return the existing
profile unchanged.

Return a single concise descriptive string, for example:
  "23-year-old female, pregnant, type 2 diabetes, takes metformin"

If there is no profile at all (no existing profile and no new info), return an
empty string.

Return ONLY the profile string. No explanation, no quotes, no markdown.
"""


async def patient_extractor_node(state: AgentState) -> dict:
    existing_profile = state.get("session_context", {}).get("patient_profile", "")
    user_message = state["messages"][-1].content

    prompt = PATIENT_EXTRACTOR_PROMPT.format(
        existing_profile=existing_profile or "(none yet)",
        user_message=user_message,
    )

    result = await _llm.ainvoke([HumanMessage(content=prompt)])
    updated_profile = result.content.strip()

    # Guard: never clear an existing profile with an empty response.
    if not updated_profile:
        updated_profile = existing_profile

    return {"session_context": {"patient_profile": updated_profile}}
