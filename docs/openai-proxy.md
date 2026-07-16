# OpenAI-compatible RLM proxy

This service adds the public HTTP boundary:

```text
application
  <-> public OpenAI-compatible /v1/chat/completions
  <-> recursive-llm RLM execution
  <-> LiteLLM
  <-> private OpenAI-compatible API
```

## Install

```bash
pip install -e '.[proxy,dev]'
```

## Configure

```bash
export RLM_PROXY_PUBLIC_API_KEY='public-secret'
export RLM_PROXY_PRIVATE_API_BASE='http://127.0.0.1:8080/v1'
export RLM_PROXY_PRIVATE_API_KEY='private-secret-or-placeholder'
export RLM_PROXY_MODEL='openai/local'
export RLM_PROXY_RECURSIVE_MODEL='openai/local'
export RLM_PROXY_MAX_DEPTH=2
```

`RLM_PROXY_PRIVATE_API_BASE` must include `/v1` when the private server expects it.

## Run

```bash
rlm-proxy --host 0.0.0.0 --port 8000
```

## Call using an OpenAI client

```python
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8000/v1", api_key="public-secret")
response = client.chat.completions.create(
    model="rlm",
    messages=[
        {"role": "system", "content": "Answer from the supplied records."},
        {"role": "user", "content": very_large_document},
        {"role": "user", "content": "List the three largest discrepancies."},
    ],
)
print(response.choices[0].message.content)
```

The final user message becomes the RLM query. All earlier message content becomes external RLM context. An optional top-level `rlm.context` string can supply context without placing it in chat history.

Streaming requests are accepted, but recursive-llm currently yields only a completed answer. The proxy therefore emits one content chunk followed by the terminal chunk and `[DONE]`; it does not fabricate token-level streaming.

## Verify

```bash
pytest tests/test_proxy_adapter.py tests/test_proxy_app.py
curl -fsS http://127.0.0.1:8000/healthz
```
