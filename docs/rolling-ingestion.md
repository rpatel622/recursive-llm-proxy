# Rolling ingestion for giant message dumps

When the final user message is very large, the proxy automatically preprocesses it before slot routing and RLM execution.

## Why

Sending an entire dump as the root query increases model prefill time and can exceed the private model's context limit. The proxy instead keeps each model call bounded while retaining the exact source text for RLM search.

```text
giant final user message
        |
        v
natural-boundary splitter
        |
        v
bounded rolling windows + compact rolling state
        |
        +--> extracted actual request
        +--> semantic metadata per window
        +--> exact raw window text
        |
        v
slot/workstream router sees extracted request
        |
        v
RLM receives searchable structured context
```

## Default behavior

Rolling ingestion is enabled by default when the final user message contains at least 24,000 characters.

Defaults:

| Setting | Default |
|---|---:|
| `threshold_chars` | 24,000 |
| `window_chars` | 12,000 |
| `overlap_chars` | 800 |
| `max_windows` | 128 |
| `metadata_chars` | 4,000 |

The splitter prefers paragraph, heading, list, and sentence boundaries. Oversized indivisible blocks use a fixed character window with overlap.

## Request controls

```json
{
  "model": "rlm",
  "messages": [
    {
      "role": "user",
      "content": "<large information dump followed by the actual request>"
    }
  ],
  "rlm": {
    "ingestion": {
      "enabled": true,
      "threshold_chars": 24000,
      "window_chars": 12000,
      "overlap_chars": 800,
      "max_windows": 128,
      "metadata_chars": 4000
    },
    "routing": {
      "mode": "auto"
    }
  }
}
```

Set `enabled` to `false` to preserve the earlier behavior.

## Per-window metadata

Each bounded model call produces:

- a short section title
- a retrieval summary
- topics and entities
- concrete facts, decisions, constraints, and open questions
- boundary/continuation information
- an updated compact rolling state
- any explicit user request found in that window

The rolling state is bounded by `metadata_chars`; earlier raw windows are never replayed into later preprocessing calls.

## Request extraction

The latest explicit request found by the rolling pass becomes the root query. If no explicit request is detected, the proxy applies a deterministic fallback that prefers trailing questions or imperative instructions.

Slot routing therefore receives the extracted request rather than the full dump.

## RLM context representation

The RLM external context contains a JSON object with global metadata and ordered chunk records. Every chunk retains both semantic metadata and exact raw text:

```json
{
  "kind": "rolling-ingested-user-dump",
  "global_metadata": {},
  "chunks": [
    {
      "chunk_id": "dump-0001",
      "title": "Deployment constraints",
      "summary": "...",
      "topics": ["deployment"],
      "entities": ["Service A"],
      "facts": ["Zero downtime is required"],
      "boundary": "Begins a deployment section",
      "text": "<exact source text>"
    }
  ]
}
```

This lets the recursive REPL search metadata first and inspect exact source text only where needed.

## Response metadata

Processed responses include:

```json
{
  "rlm": {
    "ingestion": {
      "status": "processed",
      "original_chars": 180000,
      "window_count": 17,
      "window_chars": 12000,
      "overlap_chars": 800,
      "extracted_request": "Compare the rollout plans.",
      "topics": ["deployment"],
      "entities": ["Service A"]
    }
  }
}
```

## Limits and failure behavior

- The proxy rejects a dump requiring more than `max_windows` with HTTP 400.
- Invalid window settings fail request validation.
- Private-model failures during preprocessing return HTTP 502 with type `ingestion_error`.
- Preprocessing adds one private-model call per window, trading total calls for bounded prefill size and predictable memory use.
