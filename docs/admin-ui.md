# Gradio administration UI

The optional Gradio UI is a small local control surface for one trusted operator. It does not replace the OpenAI-compatible API.

## Requirements

Current Gradio releases require Python 3.10 or newer. The proxy library itself continues to support Python 3.9.

Install the proxy and UI extras:

```bash
python -m pip install -e '.[proxy,ui]'
```

Start the proxy first, then launch the UI:

```bash
export RLM_PROXY_UI_PROXY_URL='http://127.0.0.1:8000'
export RLM_PROXY_UI_API_KEY='local-public-key'
rlm-proxy-ui --host 127.0.0.1 --port 7860
```

Open `http://127.0.0.1:7860`.

Command-line values override environment variables:

```bash
rlm-proxy-ui \
  --proxy-url http://127.0.0.1:8000 \
  --api-key local-public-key \
  --host 127.0.0.1 \
  --port 7860
```

## Configuration tab

The shared connection controls define:

- proxy base URL
- public bearer token

The slot catalog tab can load the current normalized catalog, edit it as JSON, validate it, and atomically replace the process-local catalog.

The UI does not edit the proxy process environment. Private model URL, model names, and RLM resource limits remain startup configuration for `rlm-proxy`.

## Test request tab

The test form sends a normal `/v1/chat/completions` request and exposes:

- automatic, explicit, or clarification-only routing
- explicit slot and workstream slugs
- initial and maximum turn windows
- multi-workstream and cross-slot policy
- assistant output
- routing metadata
- RLM usage statistics

This is intended for validating routing and context separation before integrating an application.

## Monitoring tab

`GET /v1/rlm/metrics` returns process-local counters:

- uptime
- total, successful, failed, and clarification requests
- average completed-request latency
- aggregate prompt and completion tokens
- slot and workstream counts
- the 50 most recent request records

The UI displays the same data through a manual refresh button.

Metrics reset when the proxy process restarts. Recent records contain request identifiers, status, routing metadata, latency, token counts, and error text. They do not contain prompts, context, or generated answers.

## Network exposure

The UI is intended for local use. Bind it to `127.0.0.1` unless another network boundary already controls access. Gradio authentication is not enabled by this fork; the proxy bearer token still protects API requests made by the UI.
