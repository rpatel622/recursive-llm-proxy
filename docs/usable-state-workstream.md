# Usable-State Workstream

## Purpose

Move the repository from a deployable prototype to a non-stub, nontrivial, directly usable recursive LLM system without overlapping the active CI-repair workstream.

This branch is intentionally documentation-and-contract only. It does not edit CI configuration, existing runtime modules, packaging files, or tests owned by the stabilization workstream.

## Definition of done

A user can install the package, start the service, ingest documents, submit a task, observe a genuine multi-step recursive execution, receive grounded citations, restart the service, and inspect the completed execution without synthetic responses or manual database intervention.

## Non-overwrite boundaries

This workstream owns new files under:

- `src/rlm_proxy/execution/`
- `tests/execution/`
- `docs/usable-state-workstream.md`

It must not modify these areas until the stabilization workstream is merged and green:

- `.github/workflows/`
- existing persistence tests
- release packaging and manifests
- existing catalog, memory, and knowledge service implementations

Integration with existing modules should initially occur through adapters and public interfaces rather than edits to their internals.

## Delivery plan

### Phase 0 — Green baseline gate

No runtime merge proceeds while `main` has failing type checks or tests. Work can continue on isolated branches, but integration requires a green baseline.

Acceptance criteria:

- Ruff passes.
- Black passes.
- Mypy passes.
- All supported Python and operating-system test jobs pass.

### Phase 1 — Execution contracts

Create explicit, typed contracts for recursive execution:

- immutable task and step identifiers
- step states and terminal outcomes
- planner proposals
- tool-call requests and results
- evidence references
- budget accounting
- execution snapshots

Acceptance criteria:

- contracts contain no provider-specific types
- objects round-trip through JSON
- invalid state transitions are rejected
- deterministic unit tests cover serialization and validation

### Phase 2 — Durable execution store

Implement a SQLite-backed execution journal using append-only events and transactional snapshots.

Required behavior:

- create an execution
- append planned steps
- claim and complete steps atomically
- record tool outputs and evidence
- enforce optimistic revision checks
- resume after process restart
- prevent duplicate completion

Acceptance criteria:

- crash-recovery tests reopen the database and continue an unfinished execution
- concurrent claims cannot assign one step twice
- completed executions are immutable except for annotations

### Phase 3 — Real recursive coordinator

Implement a coordinator that repeatedly performs:

1. inspect current execution state
2. ask a planner for the next bounded set of steps
3. execute eligible steps
4. evaluate whether the objective is satisfied
5. recurse until success, explicit failure, cancellation, or budget exhaustion

This must not be a wrapper around one model call. At least two planning/evaluation cycles must be possible and observable.

Acceptance criteria:

- recursion depth, iteration count, elapsed time, and token/tool budgets are enforced
- cancellation interrupts pending work safely
- planner output cannot bypass validation
- a deterministic fake planner is used only in tests

### Phase 4 — Grounded knowledge adapter

Connect the coordinator to the existing knowledge API through a narrow adapter.

Required behavior:

- retrieval returns stable evidence identifiers
- generated conclusions retain evidence links
- missing evidence is explicit rather than silently fabricated
- citations can be resolved after restart

Acceptance criteria:

- an end-to-end test ingests a document, retrieves it during execution, and returns a cited result
- unsupported or empty retrieval produces a typed failure or ungrounded status

### Phase 5 — Provider and tool execution

Add a provider-neutral model interface and a tool registry with explicit schemas.

Required behavior:

- model calls record inputs, outputs, usage, latency, and errors
- tool execution is allow-listed
- retries are bounded and classified
- timeouts and cancellation are enforced

Acceptance criteria:

- one local OpenAI-compatible endpoint works without code changes
- one offline deterministic provider supports test execution
- tool failures remain inspectable in the execution journal

### Phase 6 — Usable API surface

Expose execution endpoints without replacing existing APIs:

- `POST /v1/executions`
- `GET /v1/executions/{execution_id}`
- `POST /v1/executions/{execution_id}/cancel`
- `GET /v1/executions/{execution_id}/events`

Acceptance criteria:

- API responses are typed and versioned
- clients can poll or stream progress
- restart preserves status and event history
- errors are actionable and do not leak secrets

### Phase 7 — End-to-end usability gate

Create a release-blocking scenario:

1. install from a wheel in a clean environment
2. start the service
3. ingest a local document
4. submit a question requiring retrieval and at least one recursive refinement
5. receive a final answer with citations and execution trace
6. restart the service
7. retrieve the same execution and evidence

No mocks, monkeypatches, synthetic server responses, or direct database edits are allowed in this gate.

## First implementation slice

The first code PR from this workstream should contain only Phase 1:

- `src/rlm_proxy/execution/models.py`
- `src/rlm_proxy/execution/state_machine.py`
- `tests/execution/test_models.py`
- `tests/execution/test_state_machine.py`

This keeps the initial diff isolated, reviewable, and independent of the current CI failures.

## Parallel branch sequence

1. `workstream/execution-contracts`
2. `workstream/execution-store`
3. `workstream/execution-coordinator`
4. `workstream/execution-knowledge-adapter`
5. `workstream/execution-api`
6. `workstream/execution-e2e`

Each branch starts from the latest merged predecessor in this sequence, not from unrelated feature branches. Existing files are changed only in a final integration PR after the isolated modules and tests are complete.

## Merge policy

A phase is complete only when:

- its acceptance criteria are represented by tests
- no test relies on sleeps for synchronization
- no production implementation contains `pass`, `NotImplementedError`, hard-coded model output, or synthetic retrieval results
- public behavior is documented
- the phase passes the full repository CI matrix
