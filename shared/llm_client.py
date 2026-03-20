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
#   MODEL -> str                    single model used for all LLM calls (extraction, Cypher, QA)
#
# Model defaults per provider (used if MODEL env var is not set):
#   deepseek: "deepseek-chat"
#   openai:   "gpt-4o"
#
# Override by setting MODEL in .env.
