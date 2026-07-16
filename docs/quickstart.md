# Quick start: recursive-llm proxy

This fork adds an OpenAI-compatible public API, automatic slot/workstream routing, and a private OpenAI-compatible model boundary.

```text
application
  <-> http://127.0.0.1:8000/v1
  <-> slot/workstream router
  <-> recursive-llm
  <-> http://127.0.0.1:8080/v1
  <-> llama-server
```

## 1. Install

```bash
git clone https://github.com/rpatel622/recursive-llm-proxy.git
cd recursive-llm-proxy
python -m venv .venv
. .venv/bin/activate
pip install -e '.[proxy]'
```

## 2. Start the private model server

Start `llama-server` with an OpenAI-compatible `/v1` endpoint. Example:

```bash
llama-server \
  --model /models/model.gguf \
  --host 127.0.0.1 \
  --port 8080 \
  --ctx-size 32768
```

Verify it independently:

```bash
curl -fsS http://127.0.0.1:8080/v1/models
```

## 3. Configure and start the proxy

```bash
export RLM_PROXY_PUBLIC_API_KEY='local-public-key'
export RLM_PROXY_PRIVATE_API_BASE='http://127.0.0.1:8080/v1'
export RLM_PROXY_PRIVATE_API_KEY='local-private-key'
export RLM_PROXY_MODEL='openai/local'
export RLM_PROXY_RECURSIVE_MODEL='openai/local'
export RLM_PROXY_MAX_DEPTH=2

rlm-proxy --host 127.0.0.1 --port 8000
```

Verify the proxy:

```bash
curl -fsS http://127.0.0.1:8000/healthz
curl -fsS \
  -H 'Authorization: Bearer local-public-key' \
  http://127.0.0.1:8000/v1/models
```

## 4. Register slots and workstreams

Slots are isolation boundaries. Workstreams share a slot but retain distinct histories.

```bash
curl -fsS -X PUT http://127.0.0.1:8000/v1/rlm/slots \
  -H 'Authorization: Bearer local-public-key' \
  -H 'Content-Type: application/json' \
  --data @examples/proxy/slot_setup.json
```

Inspect the normalized catalog:

```bash
curl -fsS \
  -H 'Authorization: Bearer local-public-key' \
  http://127.0.0.1:8000/v1/rlm/slots
```

The catalog is process-local. Reload it after restarting the proxy.

## 5. Send an automatically routed request

```bash
curl -fsS -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H 'Authorization: Bearer local-public-key' \
  -H 'Content-Type: application/json' \
  --data @examples/proxy/auto_route.json
```

The router receives slot/workstream metadata plus a bounded recent-turn window. It may expand that window up to `max_turn_count`. It either selects context or returns a clarification containing candidate slugs.

## 6. Bypass routing with explicit slugs

```bash
curl -fsS -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H 'Authorization: Bearer local-public-key' \
  -H 'Content-Type: application/json' \
  --data @examples/proxy/explicit_route.json
```

Explicit routing is deterministic and bypasses the routing-model decision.

## 7. Use the OpenAI Python client

Install the client and run the example:

```bash
pip install openai
RLM_PROXY_API_KEY='local-public-key' python examples/proxy/openai_sdk.py
```

## 8. Launch the optional Gradio UI

Current Gradio releases require Python 3.10 or newer.

```bash
pip install -e '.[proxy,ui]'
RLM_PROXY_UI_PROXY_URL='http://127.0.0.1:8000' \
RLM_PROXY_UI_API_KEY='local-public-key' \
rlm-proxy-ui --host 127.0.0.1 --port 7860
```

Open `http://127.0.0.1:7860`. The UI can edit the slot catalog, run routed test requests, and inspect process metrics and recent request records.

## Verification

```bash
pip install -e '.[proxy,dev]'
pytest tests/test_proxy_adapter.py tests/test_proxy_app.py tests/test_proxy_routing.py tests/test_proxy_metrics.py
```

See also:

- [Gradio administration UI](admin-ui.md)
- [Slot routing](slot-routing.md)
- [API reference](api.md)
- [Architecture](architecture.md)
- [Proxy reference](openai-proxy.md)
