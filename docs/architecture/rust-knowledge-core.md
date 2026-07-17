# Rust knowledge core

This crate is the first additive step toward a binary-first Local RLM stack. It does not replace the existing Python proxy yet.

## Boundaries

The core owns stable application types and traits for:

- document extraction
- deterministic chunking
- dense embedding
- candidate reranking
- vector/lexical storage
- ingestion and search orchestration

External engines are optional adapters rather than application-level types. This prevents Xberg, FastEmbed, or Memvid API changes from leaking through the rest of the product.

## Dependency policy

- **Xberg** is the intended document extraction engine. Only format features required by the desktop product are enabled. OCR, transcription, HEIC, VLM, and Xberg embedding features remain disabled.
- **FastEmbed-rs** is the intended dense embedding and reranking engine. It is the only component allowed to own ONNX Runtime and model downloads.
- **Memvid** is a candidate portable knowledge store. It remains behind `KnowledgeStore` until crash recovery, upgrades, deletion, compaction, and external-vector insertion are validated.
- **EdgeQuake** is a design reference for Graph-RAG and retrieval evaluation, not a bundled runtime dependency. Its PostgreSQL/pgvector/AGE deployment conflicts with the single-user desktop footprint target.

## Feature flags

The crate has no default external-engine features. This keeps the foundational types and tests dependency-light.

- `xberg`: resolves the selected ingestion feature set.
- `fastembed`: resolves local embedding/reranking dependencies.
- `memvid`: resolves the lexical memory store candidate.
- `full`: resolves all candidates for compatibility checks.

Feature-specific adapters will be added only after small integration tests prove their public APIs and release packaging on Windows, macOS, and Linux.

## Migration path

1. Compile and test the engine-independent core.
2. Add Xberg extraction adapter and golden-file tests.
3. Add FastEmbed embedding/reranking adapter with an explicitly managed model cache.
4. Prototype Memvid and SQLite stores against the same conformance suite.
5. Expose ingestion and retrieval through the OpenAI-compatible proxy.
6. Move proxy and process supervision to Rust after behavior parity is established.
