# LLM client factory.
# Returns a configured OpenAI-compatible client based on LLM_PROVIDER env var.
# Both OpenAI and DeepSeek use the same openai Python SDK — only base_url, api_key, and model differ.
#
# Supported providers (set via LLM_PROVIDER):
#   "openai"   — uses OPENAI_API_KEY, base_url is default OpenAI
#   "deepseek" — uses DEEPSEEK_API_KEY, base_url is https://api.deepseek.com
#
# Exposes:
#   get_client() -> openai.OpenAI   returns the configured client
#   EXTRACTION_MODEL -> str          model to use in extractor.py (cheaper/faster)
#   QA_MODEL -> str                  model to use in qa.py and retriever.py (best quality)
#
# Model defaults per provider:
#   openai:   EXTRACTION_MODEL = "gpt-4o-mini",  QA_MODEL = "gpt-4o"
#   deepseek: EXTRACTION_MODEL = "deepseek-chat", QA_MODEL = "deepseek-chat"
#
# Models can be overridden individually via EXTRACTION_MODEL and QA_MODEL env vars.
