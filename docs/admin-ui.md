# Gradio administration UI

The optional Gradio UI is a local control surface for one trusted operator. It can configure and launch the proxy process, manage slots, run routed requests, and inspect metrics.

## Requirements

Current Gradio releases require Python 3.10 or newer. The core proxy library continues to support Python 3.9.

Install and launch:

```bash
python -m pip install -e '.[proxy,ui]'
rlm-proxy-ui
```

Open `http://127.0.0.1:7860`.

No proxy environment variables or command-line arguments are required for this path. The UI itself uses `127.0.0.1:7860` by default. Optional `--host` and `--port` arguments still control where the Gradio UI listens.

## Configuration

The Configuration tab sets the child proxy process values:

- proxy bind host and port
- public bearer token
- private OpenAI-compatible API base URL and key
- root and recursive model names
- maximum RLM depth and iterations

Press **Start / restart proxy** to validate the fields, stop any proxy previously launched by this UI, and start a new Uvicorn child process. The active proxy URL and public key are copied into the connection controls used by the remaining tabs.

The default values expect:

```text
Gradio UI:    http://127.0.0.1:7860
Public proxy: http://127.0.0.1:8000
Private API:  http://127.0.0.1:8080/v1
Models:       openai/local
```

The UI does not start `llama-server`; the configured private API must already be reachable.

A proxy launched outside the UI can still be used. Enter its URL and public key under **Active proxy connection**, then press **Check connection**.

## Process behavior

The UI owns at most one child proxy process. Restarting terminates the previous child before creating another. Stopping the UI process also terminates its operating-system process tree according to normal platform behavior; use **Stop proxy** for an orderly shutdown while the UI remains open.

Configuration values are passed directly to the child process environment and are not written to disk. The slot catalog and metrics remain process-local and reset when that proxy restarts.

## Slot catalog

The Slot catalog tab can load the current normalized catalog, edit it as JSON, validate it, and atomically replace the process-local catalog.

## Test request

The test form sends a normal `/v1/chat/completions` request and exposes:

- automatic, explicit, or clarification-only routing
- explicit slot and workstream slugs
- initial and maximum turn windows
- multi-workstream and cross-slot policy
- assistant output
- routing metadata
- RLM usage statistics

## Monitoring

`GET /v1/rlm/metrics` returns process-local counters for uptime, request outcomes, latency, tokens, catalog size, and the 50 most recent request records. The Monitoring tab displays the same data through manual refresh.

Metrics reset when the proxy process restarts. Recent records contain request identifiers, status, routing metadata, latency, token counts, and error text. They do not contain prompts, context, or generated answers.

## Network exposure

The UI is intended for local use. Bind it to `127.0.0.1` unless another network boundary controls access. Gradio authentication is not enabled by this fork; the proxy bearer token protects API requests made by the UI.
