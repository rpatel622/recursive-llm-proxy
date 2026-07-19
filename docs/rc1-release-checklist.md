# RC1 promotion checklist

A commit may be promoted to `v0.3.0rc1` only when all items below are complete.

## Automated gates

- Python quality and supported-version tests are green.
- Rust formatting, Clippy, tests, and all-feature compilation are green.
- Evaluation quality policy passes.
- RC1 system smoke passes.
- Persistence backup and restore tests pass.
- Wheel installation passes on Linux, macOS, and Windows.
- Wheel and source-distribution manifests verify without errors.

## Manual gates

- Confirm `/healthz` and `/readyz` behavior for a complete local stack.
- Confirm a memory-enabled chat survives a process restart.
- Confirm catalog export, import, backup, and audit verification through the control plane.
- Confirm one document can be ingested, searched with citations, and deleted.
- Confirm no secrets, databases, model files, or user logs are included in release artifacts.
- Record known limitations and upgrade notes in the changelog.

## Promotion

1. Run the `RC1 promotion` workflow against the intended commit.
2. Download and inspect the verified artifact bundle.
3. Create the annotated `v0.3.0rc1` tag at the exact verified commit.
4. Publish the release as a prerelease with the manifest attached.
5. Do not move or recreate the tag after publication.
