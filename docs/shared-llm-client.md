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

## Singleton pattern

Each consumer that calls the LLM in a tight loop creates one instance at module level rather than per-call:

```python
# agent/nodes/guardrail.py (and router, decision, summarizer)
_llm = get_client(temperature=0)   # created once at import time

async def guardrail_node(state):
    result = await _llm.ainvoke([...])
```

```python
# ingestion/extractor.py
async def _extract_from_chunks_async(chunks, workers, ...):
    llm = get_client(temperature=0)   # one instance for the whole extraction run
    # passed to all concurrent chunk coroutines
```

`ChatOpenAI` construction is not free — it allocates an HTTPX connection pool. Creating it once per process (agent nodes) or once per extraction run (extractor) avoids that overhead on every request.

## Concurrent async safety

A single `ChatOpenAI` instance is safe to call concurrently from multiple `async` coroutines. Each `await llm.ainvoke(prompt)` issues an independent HTTP request through the shared HTTPX async connection pool. No per-request mutable state is stored on the `ChatOpenAI` object — only read-only configuration (model, temperature, API key). This is the standard usage pattern for the OpenAI Python SDK's async client.

The extractor runs up to `EXTRACTION_MAX_WORKERS` (default 20) chunk coroutines concurrently, all sharing one `ChatOpenAI` instance. Within each coroutine, retries are awaited sequentially — they do not affect other chunks running in parallel.
