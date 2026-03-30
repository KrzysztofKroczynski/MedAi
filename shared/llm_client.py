"""
LLM client factory for LangChain.
Returns a configured ChatOpenAI instance based on LLM_PROVIDER env var.
Both OpenAI and DeepSeek use langchain-openai — only base_url, api_key, and model differ.

Supported providers (LLM_PROVIDER):
  "openai"   — OPENAI_API_KEY, default model gpt-4o-mini
  "deepseek" — DEEPSEEK_API_KEY, base_url https://api.deepseek.com, default model deepseek-chat

Override model by setting MODEL in .env.

Exposes:
  get_llm(temperature=0, **kwargs) -> ChatOpenAI
  get_client  — alias for get_llm
  MODEL       -> str
"""

import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()

_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek").lower()

_PROVIDER_CFG = {
    "openai": {
        "api_key_env": "OPENAI_API_KEY",
        "base_url": None,
        "default_model": "gpt-4o-mini",
    },
    "deepseek": {
        "api_key_env": "DEEPSEEK_API_KEY",
        "base_url": "https://api.deepseek.com",
        "default_model": "deepseek-chat",
    },
}

if _PROVIDER not in _PROVIDER_CFG:
    raise ValueError(f"Unknown LLM_PROVIDER '{_PROVIDER}'. Choose 'openai' or 'deepseek'.")

_cfg = _PROVIDER_CFG[_PROVIDER]
MODEL: str = os.getenv("MODEL", _cfg["default_model"])


def get_llm(temperature: float = 0, **kwargs) -> ChatOpenAI:
    """Return a configured LangChain ChatOpenAI instance."""
    api_key = os.getenv(_cfg["api_key_env"])
    if not api_key:
        raise EnvironmentError(
            f"Missing API key: set {_cfg['api_key_env']} for provider '{_PROVIDER}'."
        )
    init_kwargs = dict(model=MODEL, api_key=api_key, temperature=temperature, **kwargs)
    if _cfg["base_url"]:
        init_kwargs["base_url"] = _cfg["base_url"]
    return ChatOpenAI(**init_kwargs)


get_client = get_llm
