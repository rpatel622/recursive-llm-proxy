## Summary

Describe the independently releasable slice delivered by this pull request.

## Track

- [ ] A — Platform contracts
- [ ] B — Knowledge operations
- [ ] C — Runtime and packaging
- [ ] D — User interface
- [ ] E — Evaluation
- [ ] F — Performance

## Owned paths

List the repository paths this pull request intentionally changes.

## Contracts changed

List HTTP schemas, persisted schemas, process contracts, configuration keys, or fixture formats changed by this pull request. Write `None` when no contract changes are involved.

## Dependencies

List prerequisite pull requests or contracts. Prefer `None`; do not stack implementation branches unless a shared contract is required.

## Non-goals

List adjacent work intentionally excluded from this slice.

## Migration and compatibility

Describe database migration, API compatibility, upgrade, rollback, or user-data implications. Write `None` when not applicable.

## Validation

List commands and scenarios used to validate the change.

## Conflict check

- [ ] Shared-file edits are necessary and narrowly scoped.
- [ ] No unrelated refactoring is included.
- [ ] UI/runtime code uses public APIs rather than internal storage or retrieval modules.
- [ ] Performance changes preserve observable behavior and public contracts.
- [ ] Tests and documentation cover the changed contract or behavior.
