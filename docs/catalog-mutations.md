# Catalog mutation API

Catalog snapshots include a monotonically increasing `version`. Mutating requests may send that version in `expected_version` or the `If-Match` header. A stale version returns `409 Conflict` without modifying stored data.

## Append a turn

```http
POST /v1/rlm/slots/engineering/workstreams/deployment/turns
Content-Type: application/json

{
  "role": "user",
  "content": "Prepare the production rollout",
  "expected_version": 4
}
```

A successful response is the complete normalized catalog snapshot with version `5` and an `ETag: "5"` header.

## Delete a workstream

```http
DELETE /v1/rlm/slots/engineering/workstreams/deployment
If-Match: "5"
```

A successful response is the complete normalized catalog snapshot after deletion. Unknown slots or workstreams return `404 Not Found`.
