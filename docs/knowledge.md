# Native knowledge service

The native knowledge service exposes the Rust ingestion and retrieval pipeline over a loopback HTTP boundary. It is optional: the Python proxy behaves as before when `RLM_PROXY_KNOWLEDGE_API_BASE` is unset.

## Run

```bash
export RLM_KNOWLEDGE_DB="$HOME/.local/share/local-rlm/knowledge.sqlite3"
export RLM_KNOWLEDGE_BIND="127.0.0.1:8010"
cargo run -p rlm-knowledge-service
```

The first start downloads the configured FastEmbed embedding and reranking models. Later starts use the local model cache. The service binds to loopback by default.

Enable automatic retrieval in the proxy:

```bash
export RLM_PROXY_KNOWLEDGE_API_BASE="http://127.0.0.1:8010"
```

## Ingest or replace a source

Content is base64 encoded so the same endpoint supports text, HTML, PDF, DOCX, and XLSX without multipart parsing.

```http
POST /v1/knowledge/ingest
Content-Type: application/json

{
  "source_uri": "file:///home/user/notes.pdf",
  "media_type": "application/pdf",
  "content_base64": "..."
}
```

Re-ingesting the same `source_uri` replaces every previous document version before the new chunks become searchable. Extraction, chunking, and embedding complete before replacement begins.

## Search and prompt context

```http
POST /v1/knowledge/search
Content-Type: application/json

{
  "query": "What is the rollback procedure?",
  "candidate_limit": 24,
  "limit": 6,
  "rerank": true,
  "max_context_chars": 24000
}
```

The response contains:

- reranked search hits;
- stable citation records with document and chunk IDs;
- a bounded prompt-ready context string using `[Source N: label]` markers.

Retrieval combines FTS5 and cosine-vector rankings with reciprocal-rank fusion before optional cross-encoder reranking.

## Document lifecycle

```text
GET    /v1/knowledge/documents
DELETE /v1/knowledge/documents/{document_id}
GET    /v1/knowledge/stats
GET    /healthz
```

## Chat request controls

When the proxy has a knowledge service configured, retrieval is enabled by default. A request may override it:

```json
{
  "model": "rlm",
  "messages": [{"role": "user", "content": "What is the rollback procedure?"}],
  "rlm": {
    "knowledge": {
      "enabled": true,
      "candidate_limit": 32,
      "limit": 8,
      "rerank": true,
      "max_context_chars": 20000,
      "required": false
    }
  }
}
```

When `required` is false, an unavailable knowledge service is recorded in `rlm.knowledge` and the chat continues without retrieved context. When it is true, the proxy returns a `502 knowledge_error`.

Successful responses include citation metadata:

```json
{
  "rlm": {
    "knowledge": {
      "status": "ok",
      "hit_count": 3,
      "citations": [
        {
          "index": 1,
          "document_id": "doc-...",
          "chunk_id": "doc-...:0",
          "source_uri": "file:///home/user/notes.pdf",
          "title": "notes.pdf",
          "score": 0.91
        }
      ]
    }
  }
}
```

The proxy assembles context in this order: selected routed context, retrieved knowledge, then explicit/request-message context. A routing clarification returns before knowledge retrieval or model execution.
