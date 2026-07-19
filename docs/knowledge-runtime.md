# Managed knowledge runtime

The cowork launcher can supervise `rlm-knowledge-service` as part of the local stack.

Configuration:

- `RLM_COWORK_KNOWLEDGE_BINARY`
- `RLM_COWORK_KNOWLEDGE_HOST`
- `RLM_COWORK_KNOWLEDGE_PORT`
- `RLM_COWORK_KNOWLEDGE_DATA_DIR`
- `RLM_COWORK_KNOWLEDGE_ENABLED`

The default database is stored at `~/.recursive-llm/knowledge/knowledge.sqlite3`. Logs are written beside it as `knowledge-service.log`. These files live outside the release bundle so repair and upgrades do not remove indexed documents.

Startup order is knowledge service, llama-server, proxy, then Open WebUI. Shutdown uses the reverse dependency order. The proxy receives the managed service URL through `RLM_PROXY_KNOWLEDGE_API_BASE`.

Startup waits for `GET /healthz` to return `{ "status": "ok" }`. Early process exits and health timeouts report the log path for diagnosis.
