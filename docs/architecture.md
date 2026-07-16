# Architecture

## Components

```text
OpenAI-compatible client
        |
        v
FastAPI public boundary
        |
        +--> slot catalog
        |
        +--> routing pass
        |      metadata + bounded recent turns
        |      route / expand / clarify
        |
        +--> selected-context builder
        |
        v
recursive-llm RLM runtime
        |
        v
LiteLLM OpenAI-compatible client
        |
        v
private model server, such as llama-server
```

## Request lifecycle

1. Validate the OpenAI-compatible request and optional public bearer token.
2. Extract the final user message as the RLM query.
3. Resolve context:
   - use explicit slugs when supplied;
   - otherwise route against the catalog;
   - otherwise use direct `rlm.context` and earlier request messages.
4. If routing is ambiguous, return a clarification without executing the RLM.
5. Construct context from only the selected slot and workstreams.
6. Create an `RLM` instance with configured execution limits.
7. Execute against the private OpenAI-compatible endpoint through LiteLLM.
8. Return an OpenAI-compatible response with RLM statistics and routing metadata.

## Separation boundary

Slots are the isolation boundary. The selected-context builder omits every unselected slot before RLM execution.

Workstreams are organizational boundaries inside a slot. Multiple selected workstreams can be combined because they belong to the same shared domain.

This is context isolation, not a security boundary. The current deployment assumes a trusted single user.

## Routing lifecycle

```text
metadata + last N turns
        |
        v
model routing decision
   | route
   | expand to min(2N, max N)
   | clarify
```

The server, not the model, enforces maximum expansion and cross-slot policy. Routing operates against an immutable catalog snapshot for the duration of a request.

## State

The slot catalog is process-local memory. `PUT /v1/rlm/slots` replaces the entire catalog atomically. This yields deterministic reads but no restart persistence.

A future persistence adapter should preserve the same normalized catalog interface and provide atomic snapshot replacement or versioned transactions.

## Failure boundaries

- Catalog validation fails before routing.
- Routing ambiguity returns a clarification rather than guessing.
- Invalid explicit slugs fail before RLM execution.
- RLM budgets apply to the selected execution tree.
- Private provider failures surface as gateway errors.

## Extension points

Suitable future additions include:

- durable SQLite or PostgreSQL catalog storage
- append-only turn endpoints
- catalog version identifiers
- per-slot RLM budgets
- isolated-per-slot execution followed by synthesis
- embedding-assisted candidate narrowing before model routing
- background metadata refresh outside the request path
