# Parallel delivery plan

This plan reorganizes the remaining work around stable dependency boundaries rather than sequential subsystem phases. The goal is maximum parallel progress with minimal merge conflicts, contract churn, and implementation writeover.

## Operating rules

1. Public HTTP schemas, persisted schemas, and process contracts are changed only through small contract PRs.
2. Contract changes are additive by default. Breaking changes require migration notes and compatibility tests.
3. Each implementation PR owns a narrow path set and avoids unrelated refactors.
4. UI and runtime code consume public APIs and never import storage or retrieval internals.
5. Performance work replaces implementations behind existing interfaces; it does not change observable behavior.
6. Every feature is delivered as a vertical slice with tests, documentation, and failure handling.
7. Shared contract PRs merge before dependent implementation PRs. All other tracks proceed concurrently.

## Track map

| Track | Scope | Primary ownership | Hard dependencies |
|---|---|---|---|
| A — Platform contracts | catalog mutations, import/export, migrations, events | `src/rlm_proxy/models.py`, `src/rlm_proxy/catalog_store.py`, API schemas | none |
| B — Knowledge operations | asynchronous ingestion, collections, synchronization | `rust/knowledge-core`, `rust/knowledge-service` | approved API contracts only |
| C — Runtime and packaging | supervision, data directories, logs, release bundles | launchers, bundled runtime, release workflows | service health/process contracts |
| D — User interface | API clients and management surfaces | control UI and browser-facing code | published APIs |
| E — Evaluation | routing, retrieval, grounding, latency regression | evaluation fixtures, benchmark scripts, CI jobs | stable response schemas |
| F — Performance | profiling, caches, ANN/vector backend adapters | internal retrieval implementations | B interfaces frozen |

## Branch and PR policy

Use one branch per independently mergeable slice:

- `contract/<area>-<change>` for shared schemas and interfaces
- `feat/platform-<slice>`
- `feat/knowledge-<slice>`
- `feat/runtime-<slice>`
- `feat/ui-<slice>`
- `test/eval-<slice>`
- `perf/<slice>`

A PR must list:

- owned paths
- APIs or schemas changed
- dependencies
- explicit non-goals
- migration impact
- validation commands

Do not stack implementation branches unless a shared contract is genuinely required. Prefer a small contract PR followed by sibling implementation PRs from `main`.

## First parallel wave

The following slices can begin after this plan lands.

### A1 — Complete catalog mutation API

Deliver:

- append-turn HTTP endpoint
- delete-workstream HTTP endpoint
- optimistic version input and `409 Conflict` responses
- request/response examples
- API tests

Owned paths:

- `src/rlm_proxy/app.py`
- `src/rlm_proxy/models.py`
- catalog API tests
- `docs/api.md`

Non-goals:

- UI
- import/export
- conversation summarization

### A2 — Catalog import/export and backup contract

Deliver:

- deterministic JSON export
- validated import
- database backup operation
- schema and catalog version metadata
- round-trip and corrupt-input tests

Avoid editing A1 endpoint handlers except for additive route registration.

### B1 — Background knowledge ingestion jobs

Deliver:

- persisted job model
- queued/running/succeeded/failed/cancelled states
- enqueue, status, list, and cancel endpoints
- bounded worker concurrency
- restart recovery policy
- tests using deterministic fake extractors/embedders

Non-goals:

- directory watching
- UI
- ANN indexing

### C1 — Knowledge-service supervision

Deliver:

- launch and terminate the Rust knowledge service with the local stack
- health checks
- user-data database path
- startup failure diagnostics
- preservation across repair and upgrade
- cross-platform packaging validation

This track consumes the service health contract and does not alter retrieval code.

### D1 — Typed API client foundation

Deliver:

- isolated clients for catalog and knowledge APIs
- version-conflict and service-unavailable handling
- mock server fixtures
- no direct database access

The first UI PR should not redesign screens. It establishes the client boundary so visual work can proceed independently.

### E1 — Evaluation harness foundation

Deliver:

- versioned fixture format
- deterministic routing tests
- retrieval relevance fixtures
- grounded citation assertions
- machine-readable result output
- a non-blocking CI job initially

Evaluation code must not patch production algorithms to make fixtures pass.

### F1 — Retrieval profiling baseline

Deliver:

- corpus-size and latency benchmark runner
- ingestion throughput measurements
- vector search and reranking timing separation
- memory and database-size reporting
- saved baseline format

No algorithm change belongs in this slice.

## Second wave

Begin when the relevant first-wave contract is stable:

- A3: migration command and restore tooling
- B2: collections, namespaces, and metadata filters
- B3: incremental file synchronization and deduplication
- C2: process restart policy, log rotation, and diagnostics bundle
- D2: knowledge document browser and ingestion progress UI
- D3: slot/workstream editor and append-turn UI
- E2: quality thresholds and blocking regression gates
- F2: embedding/query caches behind existing traits
- F3: ANN backend adapter with equivalence tests

## Integration checkpoints

### Checkpoint 1 — Contracts

- catalog mutation APIs documented and tested
- ingestion job schemas documented
- process health and data-path contracts documented
- fixture formats versioned

### Checkpoint 2 — Usable operations

- background ingestion works without UI
- runtime supervises all local services
- API client can exercise catalog and knowledge flows
- evaluation reports are generated in CI

### Checkpoint 3 — Product slice

- user can ingest, inspect, search, and delete knowledge from the browser
- conversations persist through append APIs
- restart preserves catalog and knowledge state
- quality and performance baselines are recorded

## Conflict prevention

Before editing a shared file, a PR should state why the change cannot be isolated. Common shared files should be kept thin:

- `app.py` registers routes and delegates to feature modules.
- `models.py` contains transport contracts only; domain implementation types live with their modules.
- workflow files call reusable scripts rather than embedding large logic blocks.
- UI components use typed clients rather than duplicating endpoint details.

When two slices need the same shared file, extract the shared contract in a small prerequisite PR, merge it, then restart both slices from the updated `main`.

## Definition of complete

The parallel program is complete when:

- all public APIs are documented and compatibility-tested
- ingestion and conversation updates are asynchronous or append-oriented where appropriate
- runtime supervises and packages all services
- the browser exposes the primary catalog and knowledge workflows
- evaluation gates protect routing, retrieval, grounding, and latency
- performance backends can change without affecting API consumers
- installation, repair, backup, restore, and upgrade preserve user data
