# Slot and workstream routing

## Data model

A slot is an isolated context domain. A workstream is a distinct history inside one slot.

```text
slot
  shared slot metadata
  workstream A
    ordered turns
  workstream B
    ordered turns
```

The proxy never places unselected slots into the RLM context. Multiple workstreams may be selected inside one slot. Automatic cross-slot selection is disabled unless the request explicitly enables it.

## Stable identifiers

`slug` is the stable machine identifier. Names and descriptions are display and routing metadata.

- Slugs must be unique at their scope.
- Duplicate slot slugs are rejected.
- Duplicate workstream slugs inside a slot are rejected.
- Omitted names are generated deterministically from slugs.
- Omitted descriptions are generated deterministically from recent turn content.

Applications should persist and send slugs, not generated names.

## Catalog replacement

`PUT /v1/rlm/slots` replaces the complete process-local catalog atomically. This avoids partially updated routing state.

The current implementation does not persist the catalog. Re-register it after process restart.

## Routing modes

### `auto`

The model selects a slot and one or more workstreams. The routing pass receives:

- slot slug, name, and description
- workstream slug, name, and description
- the last N turns from each workstream
- the current user query

The router does not receive complete histories initially.

### `explicit`

The request supplies `slot_slug` and `workstream_slugs`. The proxy validates them and bypasses automatic routing.

Use explicit routing when the application already knows the destination or after the user resolves a clarification.

### `clarify_only`

The router may propose candidates but does not silently select an ambiguous destination. Use this mode when a routing mistake is more costly than an additional turn.

## Adaptive turn expansion

Automatic routing begins with `initial_turn_count`. When recent turns do not distinguish candidates, the router may request more history. The proxy doubles the window until it reaches `max_turn_count`.

Example sequence:

```text
4 -> 8 -> 16 -> 32 -> 64
```

Expansion is bounded. The router cannot request arbitrary full-history access beyond the request limit.

## Clarification

When ambiguity remains, the proxy returns an assistant message listing candidate slugs. The response also includes structured routing metadata.

Example message:

```text
I found multiple plausible workstreams:

- engineering/deployment-prod
- engineering/deployment-staging

Specify the slot and workstream slug to continue.
```

The next request should use explicit routing:

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

## Context construction

After routing resolves, the RLM receives only:

1. selected slot metadata
2. selected workstream metadata and histories
3. optional `rlm.context`
4. earlier messages from the current OpenAI-compatible request

The final user message is the RLM query.

## Multiple workstreams

When `allow_multi_workstream` is true, automatic routing may select several workstreams in the same slot. This supports comparison and synthesis without weakening slot isolation.

A request that truly spans slots should either:

- explicitly name those slots, or
- set `allow_cross_slot` and accept the weaker separation boundary

For predictable behavior, keep `allow_cross_slot` false and perform separate RLM runs followed by synthesis.

## Recommended operating rules

- Use one slot per genuinely isolated domain.
- Create separate workstreams for orthogonal threads that may still need comparison.
- Keep slugs stable after creation.
- Prefer explicit routing for UI-selected workstreams.
- Use automatic routing for free-form chat entry.
- Preserve routing metadata with application logs.
- Re-register the catalog after every proxy restart.
