# Shared — LLM Client (`shared/llm_client.py`)

[← Overview](./ingestion-overview.md)

## Purpose

Factory for LangChain LLM instances. Supports OpenAI and DeepSeek via a unified interface.

## Configuration

```bash
LLM_PROVIDER=deepseek   # or openai
DEEPSEEK_API_KEY=sk_... # required if using DeepSeek
OPENAI_API_KEY=sk_...   # required if using OpenAI
MODEL=deepseek-chat     # optional override (defaults per provider below)
```

| Provider | Default model | Base URL |
|----------|--------------|----------|
| `openai` | `gpt-4o-mini` | *(OpenAI default)* |
| `deepseek` | `deepseek-chat` | `https://api.deepseek.com` |

## Usage

```python
from shared.llm_client import get_client, MODEL

llm = get_client(temperature=0)   # deterministic — used for extraction
response = llm.invoke("prompt")
print(MODEL)                       # active model name
```

`get_llm` and `get_client` are aliases.

Raises `EnvironmentError` if the required API key environment variable is not set.
