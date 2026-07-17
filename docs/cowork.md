# Browser cowork interface

The optional cowork extra launches a persistent Open WebUI instance configured to use the local recursive-llm proxy as its OpenAI-compatible provider.

## Install

Open WebUI currently requires Python 3.11 or newer for this integration.

```bash
python -m pip install -e '.[proxy,ui,cowork]'
```

Start the proxy from the administration UI:

```bash
rlm-proxy-ui
```

After the proxy is running, start the full browser interface:

```bash
rlm-cowork
```

The browser opens at `http://127.0.0.1:3000` by default.

## Defaults

The launcher configures:

- the local proxy at `http://127.0.0.1:8000/v1` as the OpenAI-compatible provider
- the `rlm` public model for chat and background task generation
- persistent Open WebUI data under `~/.recursive-llm/open-webui`
- single-user local mode without a login screen
- OpenAI-compatible providers enabled and Ollama integration disabled
- context compaction enabled for long-running browser conversations
- one Open WebUI worker to keep local SQLite and vector storage predictable

The interface includes normal chat history, workspaces, document knowledge, prompt presets, tools, and other features supplied by Open WebUI. Proxy rolling ingestion remains useful for one-off giant text dumps sent directly in a message.

## Custom connection

```bash
rlm-cowork \
  --proxy-url http://127.0.0.1:9000 \
  --api-key local-public-key \
  --port 3100
```

Use `--auth` to enable Open WebUI accounts for a fresh data directory:

```bash
rlm-cowork --auth --data-dir ~/.recursive-llm/open-webui-authenticated
```

Open WebUI does not support changing an existing installation from authenticated mode to unauthenticated mode after users have been created. Use a separate data directory when changing that choice.

## Environment variables

| Variable | Default |
|---|---|
| `RLM_COWORK_HOST` | `127.0.0.1` |
| `RLM_COWORK_PORT` | `3000` |
| `RLM_COWORK_PROXY_URL` | `http://127.0.0.1:8000` |
| `RLM_COWORK_PROXY_API_KEY` | empty |
| `RLM_COWORK_DATA_DIR` | `~/.recursive-llm/open-webui` |
| `RLM_COWORK_AUTH` | `false` |
| `RLM_COWORK_SECRET_KEY` | generated for the process |

Set a persistent `RLM_COWORK_SECRET_KEY` when authenticated sessions must survive reinstallations or environment changes.

## Security boundary

The cowork launcher does not enable terminal or computer-control services. Open WebUI tools, MCP servers, Open Terminal, and Open WebUI Computer can execute actions outside the chat process and should be installed only through an explicit capability setup flow.

The default service binds to loopback. Binding to `0.0.0.0` exposes the interface to the local network and should be combined with authentication and appropriate host firewall rules.

## Stopping

Press `Ctrl+C` in the `rlm-cowork` process. The launcher terminates its managed Open WebUI child process cleanly and leaves the persistent data directory intact.
