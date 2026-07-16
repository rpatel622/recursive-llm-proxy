# OpenAI-compatible RLM proxy

This service adds the public HTTP boundary:

```text
application
  <-> public OpenAI-compatible /v1/chat/completions
  <-> slot and workstream router
  <-> recursive-llm RLM execution
  <-> LiteLLM
  <-> private OpenAI-compatible API
```

## Install and run

```bash
pip install -e '.[proxy,dev]'
export RLM_PROXY_PUBLIC_API_KEY='public-secret'
export RLM_PROXY_PRIVATE_API_BASE='http://127.0.0.1:8080/v1'
export RLM_PROXY_PRIVATE_API_KEY='private-secret-or-placeholder'
export RLM_PROXY_MODEL='openai/local'
export RLM_PROXY_RECURSIVE_MODEL='openai/local'
rlm-proxy --host 0.0.0.0 --port 8000
```

## Register isolated slots

The process-local catalog is replaced atomically with `PUT /v1/rlm/slots`. Slugs are stable identifiers. Omitted names are generated from slugs; omitted descriptions are generated deterministically from recent turns.

```json
{
  "slots": [
    {
      "slug": "engineering",
      "workstreams": [
        {
          "slug": "deployment-prod",
          "turns": [
            {"role": "user", "content": "Production rollback planning"},
            {"role": "assistant", "content": "Use the blue-green rollback path"}
          ]
        },
        {
          "slug": "deployment-staging",
          "turns": [
            {"role": "user", "content": "Staging validation"}
          ]
        }
      ]
    }
  ]
}
```

`GET /v1/rlm/slots` returns the normalized catalog. The catalog is in memory and must be reloaded after process restart.

## Automatic routing

```json
{
  "model": "rlm",
  "messages": [
    {"role": "user", "content": "What is the rollback plan?"}
  ],
  "rlm": {
    "routing": {
      "mode": "auto",
      "initial_turn_count": 4,
      "max_turn_count": 64,
      "allow_multi_workstream": true,
      "allow_cross_slot": false
    }
  }
}
```

The router first sees slot/workstream metadata and the last `initial_turn_count` turns. It may double the turn window up to `max_turn_count`. It then either selects workstreams in one slot or returns an assistant clarification listing candidate `slot/workstream` slugs. Implicit cross-slot routing is disabled by default.

The response includes the decision:

```json
{
  "rlm": {
    "routing": {
      "status": "route",
      "slot_slug": "engineering",
      "workstream_slugs": ["deployment-prod"],
      "loaded_turn_count": 8,
      "candidate_slugs": [],
      "reason": "production is explicit"
    }
  }
}
```

## Explicit routing

Explicit slugs bypass the routing model and are validated before RLM execution:

```json
{
  "rlm": {
    "routing": {
      "mode": "explicit",
      "slot_slug": "engineering",
      "workstream_slugs": ["deployment-prod"]
    }
  }
}
```

Only the selected slot metadata and selected workstream histories enter the RLM context. Other slots and workstreams are omitted.

## Chat behavior

The final user message becomes the RLM query. Earlier request messages and optional `rlm.context` are appended after the resolved routed context. Streaming requests emit one completed content chunk followed by the terminal chunk and `[DONE]`.

## Verify

```bash
pytest tests/test_proxy_adapter.py tests/test_proxy_app.py tests/test_proxy_routing.py
curl -fsS http://127.0.0.1:8000/healthz
```
