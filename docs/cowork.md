# Browser cowork interface

The optional cowork extra launches a persistent Open WebUI instance configured to use the recursive-llm proxy. It can also manage a local `llama-server`, making the model server, proxy, and browser interface one supervised stack.

## Install

Open WebUI currently requires Python 3.11 or newer for this integration.

```bash
python -m pip install -e '.[proxy,ui,cowork]'
```

Install an official llama.cpp release and download a GGUF model. The automatic release and Hugging Face download flow is tracked separately; this implementation accepts an installed `llama-server` binary and an existing GGUF file.

## Start the complete local stack

```bash
rlm-cowork --model ~/Models/model.gguf
```

The launcher starts, in order:

1. `llama-server` at `http://127.0.0.1:8080/v1`
2. the recursive-llm proxy at `http://127.0.0.1:8000`
3. Open WebUI at `http://127.0.0.1:3000`

The browser opens automatically. Press `Ctrl+C` to stop all three child processes in reverse order.

When `llama-server` is not on `PATH`, provide it explicitly:

```bash
rlm-cowork \
  --llama-binary ~/.recursive-llm/runtime/llama-server \
  --model ~/Models/model.gguf
```

## llama.cpp defaults

The managed server uses the accessibility-first defaults:

```text
--cache-type-k q8_0
--cache-type-v q4_0
--parallel 1
--n-gpu-layers all
--ctx-size 16384
```

They can be overridden when a machine or model requires different settings:

```bash
rlm-cowork \
  --model ~/Models/model.gguf \
  --context-size 8192 \
  --gpu-layers 24 \
  --cache-type-k f16 \
  --cache-type-v f16
```

This PR does not yet implement automatic retry after GPU-memory or quantized-KV-cache startup failures. The planned installer and recovery layer will add those fallbacks.

## Connect to an existing proxy

Omit `--model` to retain the original connection-only behavior:

```bash
rlm-cowork \
  --proxy-url http://127.0.0.1:9000 \
  --api-key local-public-key \
  --port 3100
```

## Open WebUI defaults

The launcher configures:

- the local proxy as the OpenAI-compatible provider
- the `rlm` public model for chat and background task generation
- persistent Open WebUI data under `~/.recursive-llm/open-webui`
- single-user local mode without a login screen
- OpenAI-compatible providers enabled and Ollama integration disabled
- context compaction enabled for long-running browser conversations
- one Open WebUI worker to keep local SQLite and vector storage predictable

The interface includes chat history, workspaces, document knowledge, prompt presets, tools, and other Open WebUI features. Proxy rolling ingestion remains useful for one-off giant text dumps sent directly in a message.

Use `--auth` to enable Open WebUI accounts for a fresh data directory:

```bash
rlm-cowork --model ~/Models/model.gguf --auth \
  --data-dir ~/.recursive-llm/open-webui-authenticated
```

Open WebUI does not support changing an existing installation from authenticated mode to unauthenticated mode after users have been created. Use a separate data directory when changing that choice.

## Environment variables

| Variable | Default |
|---|---|
| `RLM_COWORK_HOST` | `127.0.0.1` |
| `RLM_COWORK_PORT` | `3000` |
| `RLM_COWORK_PROXY_URL` | `http://127.0.0.1:8000` |
| `RLM_COWORK_PROXY_API_KEY` | generated when managing the proxy |
| `RLM_COWORK_DATA_DIR` | `~/.recursive-llm/open-webui` |
| `RLM_COWORK_AUTH` | `false` |
| `RLM_COWORK_MODEL` | empty; existing-proxy mode |
| `RLM_COWORK_LLAMA_BINARY` | `llama-server` |
| `RLM_COWORK_LLAMA_HOST` | `127.0.0.1` |
| `RLM_COWORK_LLAMA_PORT` | `8080` |
| `RLM_COWORK_CONTEXT_SIZE` | `16384` |
| `RLM_COWORK_PARALLEL` | `1` |
| `RLM_COWORK_CACHE_TYPE_K` | `q8_0` |
| `RLM_COWORK_CACHE_TYPE_V` | `q4_0` |
| `RLM_COWORK_GPU_LAYERS` | `all` |
| `RLM_COWORK_PROXY_HOST` | `127.0.0.1` |
| `RLM_COWORK_PROXY_PORT` | `8000` |
| `RLM_COWORK_SECRET_KEY` | generated for the process |

Set a persistent `RLM_COWORK_SECRET_KEY` when authenticated sessions must survive reinstallations or environment changes.

## Security boundary

The cowork launcher does not enable terminal or computer-control services. Open WebUI tools, MCP servers, Open Terminal, and Open WebUI Computer can execute actions outside the chat process and should be installed only through an explicit capability setup flow.

All three managed services bind to loopback by default. Binding any service to `0.0.0.0` exposes it to the local network and should be combined with authentication and appropriate host firewall rules.

## Stopping

Press `Ctrl+C` in the `rlm-cowork` process. The launcher terminates Open WebUI, the proxy, and `llama-server`, while preserving the Open WebUI data directory and GGUF model file.
