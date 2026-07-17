# Gradio local control surface

The Gradio UI is the primary setup surface for one trusted local operator. It can now start the complete local stack without requiring llama.cpp, proxy, or Open WebUI command-line flags.

## Install and launch

Current Gradio releases require Python 3.10 or newer. The complete cowork stack requires Python 3.11 or newer.

```bash
python -m pip install -e '.[proxy,ui,cowork]'
rlm-proxy-ui
```

Open `http://127.0.0.1:7860`.

## One-click local stack

The first tab asks for only two essential values:

- a local `.gguf` model file
- the `llama-server` executable, which defaults to `llama-server` on `PATH`

Press **Start complete stack**. The UI validates configuration and starts:

1. `llama-server`
2. the recursive-llm OpenAI-compatible proxy
3. Open WebUI

The Open WebUI URL is shown in the tab and opens automatically by default. The active proxy URL and public API key are copied into the shared connection controls used by the testing, workspace, and monitoring tabs.

Default endpoints:

```text
Gradio control surface: http://127.0.0.1:7860
llama-server:           http://127.0.0.1:8080/v1
RLM proxy:              http://127.0.0.1:8000
Open WebUI:             http://127.0.0.1:3000
```

## Hidden complexity and defaults

Advanced settings are grouped into closed accordions so the default path does not require understanding llama.cpp flags.

The default llama.cpp runtime values are:

```text
context size: 16384
parallel slots: 1
K cache: q8_0
V cache: q4_0
GPU layers: all
```

The tab also exposes optional controls for:

- llama.cpp host and port
- context size and parallel slots
- K/V cache quantization
- GPU layer offload
- proxy host, port, public key, recursion depth, and iterations
- Open WebUI host, port, persistent data directory, browser opening, and accounts

If any service fails during startup, the UI stops all partially started services and shows the error. **Stop complete stack** shuts down Open WebUI, the proxy, and llama-server in reverse order.

## Advanced proxy

The Advanced proxy tab remains available for users who already run an OpenAI-compatible model endpoint. It configures and starts only the proxy and supports custom URLs, keys, models, and RLM limits.

## Shared connection

The connection controls at the top of the page identify the currently active proxy. They can also point at a proxy launched outside the UI. **Check connection** verifies health and model discovery.

## Workspaces

The Workspaces tab is the advanced slot/workstream catalog editor. It loads, edits, validates, and atomically replaces the process-local catalog as JSON.

## Test request

The test form sends `/v1/chat/completions` requests and exposes automatic or explicit routing, workspace/workstream selection, routing metadata, assistant output, and RLM usage statistics.

## Monitoring

The Monitoring tab displays process-local uptime, request outcomes, latency, token totals, workspace counts, and recent request records. Prompt, context, and generated answer content are not retained in metrics.

## Current limits

The UI does not yet download llama.cpp releases or search and download Hugging Face GGUF files. The binary and model must currently exist locally. Automatic installation and hardware-aware fallback remain follow-on work.

All services bind to loopback by default. Do not expose the control surface or unauthenticated Open WebUI instance to a network without an appropriate authentication and firewall boundary.
