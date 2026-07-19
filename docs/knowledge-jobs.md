# Background knowledge ingestion jobs

`knowledge-jobs` is a companion binary for `rlm-knowledge-service`. It persists ingestion requests in SQLite and forwards them to the retrieval service with bounded concurrency.

Default addresses:

- retrieval service: `http://127.0.0.1:8010`
- job service: `http://127.0.0.1:8011`

Environment variables:

- `RLM_KNOWLEDGE_API_BASE`
- `RLM_KNOWLEDGE_JOBS_BIND`
- `RLM_KNOWLEDGE_JOBS_DB`
- `RLM_KNOWLEDGE_JOB_CONCURRENCY`

Endpoints:

- `POST /v1/knowledge/jobs`
- `GET /v1/knowledge/jobs`
- `GET /v1/knowledge/jobs/{job_id}`
- `DELETE /v1/knowledge/jobs/{job_id}`
- `GET /healthz`

Jobs move through `queued`, `running`, `succeeded`, `failed`, and `cancelled`. Jobs left in `running` state after interruption are returned to `queued` during startup.
