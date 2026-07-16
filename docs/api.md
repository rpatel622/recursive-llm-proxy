# Proxy API reference

All protected endpoints accept:

```http
Authorization: Bearer <RLM_PROXY_PUBLIC_API_KEY>
```

Authentication is disabled when `RLM_PROXY_PUBLIC_API_KEY` is unset.

## `GET /healthz`

Returns process health without contacting the private model server.

```json
{"status":"ok"}
```

## `GET /v1/models`

Returns the configured public model record.

## `PUT /v1/rlm/slots`

Replaces the process-local slot catalog.

```json
{
  "slots": [
    {
      "slug": "engineering",
      "name": "Engineering",
      "description": "Engineering decisions and implementation work",
      "workstreams": [
        {
          "slug": "deployment-prod",
          "name": "Production Deployment",
          "description": "Production rollout and rollback planning",
          "turns": [
            {"role": "user", "content": "Plan the release"},
            {"role": "assistant", "content": "Use blue-green deployment"}
          ]
        }
      ]
    }
  ]
}
```

Names and descriptions may be omitted. Slugs are required and validated. Duplicate identifiers return HTTP 400.

## `GET /v1/rlm/slots`

Returns the normalized current catalog. Turn histories may be represented according to the server response model; do not treat this endpoint as durable storage.

## `POST /v1/chat/completions`

Accepts an OpenAI-compatible chat-completion request plus an optional `rlm` extension.

### Automatic routing

```json
{
  "model": "rlm",
  "messages": [
    {"role": "user", "content": "What is the production rollback plan?"}
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

### Explicit routing

```json
{
  "model": "rlm",
  "messages": [
    {"role": "user", "content": "Summarize unresolved risks."}
  ],
  "rlm": {
    "routing": {
      "mode": "explicit",
      "slot_slug": "engineering",
      "workstream_slugs": ["deployment-prod"]
    }
  }
}
```

### Direct context without catalog routing

```json
{
  "model": "rlm",
  "messages": [
    {"role": "user", "content": "Extract the decision."}
  ],
  "rlm": {
    "context": "Large external context"
  }
}
```

### RLM execution controls

The `rlm` object may include:

| Field | Meaning |
|---|---|
| `max_depth` | Maximum recursive capability depth |
| `max_iterations` | Maximum REPL iterations per RLM node |
| `max_total_calls` | Provider-call cap for the recursion tree |
| `max_total_tokens` | Reported token cap |
| `max_elapsed_seconds` | Shared run deadline |

### Routing response metadata

Successful and clarification responses include an `rlm.routing` object similar to:

```json
{
  "status": "route",
  "slot_slug": "engineering",
  "workstream_slugs": ["deployment-prod"],
  "loaded_turn_count": 8,
  "candidate_slugs": [],
  "reason": "The request explicitly refers to production rollback."
}
```

Possible statuses include routing success and clarification-required states.

### Clarification behavior

When routing remains ambiguous after bounded history expansion, the endpoint returns a normal assistant choice asking the caller to select from candidate slugs. Submit the selected slugs in a subsequent explicit-routing request.

### Streaming

`stream: true` is accepted. Recursive execution currently completes before output is available, so the proxy sends one content chunk, a terminal chunk, and `[DONE]`. It does not simulate token-level generation.

## Error behavior

| Status | Cause |
|---:|---|
| 400 | Invalid catalog, slug, routing request, or messages |
| 401 | Invalid public bearer token |
| 422 | Request schema validation failure |
| 502 | RLM or private model execution failure |

Error bodies use FastAPI's `detail` field. Applications should log the HTTP status and body rather than parsing human-readable text alone.
