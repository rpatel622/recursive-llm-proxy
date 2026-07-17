# The Local RLM control screen

The control screen is where you choose the local model and start or stop the complete browser workspace. Most people only need the first tab.

## Open the control screen

Use the launcher for your operating system:

- Windows: `launchers/windows/Start Local RLM Cowork.vbs`
- macOS: `launchers/macos/Local RLM Cowork.app`
- Linux: `launchers/linux/Start Local RLM Cowork.desktop`

Press **Set up and open** in the small launcher window. It prepares a private application environment and opens:

```text
http://127.0.0.1:7860
```

No terminal interaction is required.

## One-click local stack

The first tab asks for two essential values:

- **GGUF model file:** the local AI model you downloaded
- **llama-server executable:** the server program from the llama.cpp release

When `llama-server` is already available to the system, leave the default value unchanged.

Press **Start complete stack**. The control screen starts:

1. the local model server;
2. the Recursive Language Model layer;
3. the Open WebUI browser workspace.

Open WebUI normally appears automatically. Its default address is:

```text
http://127.0.0.1:3000
```

## What the status panel means

The status panel reports each local service separately:

| Service | What it does |
|---|---|
| llama-server | Loads and runs the GGUF model |
| RLM proxy | Handles long context, recursive work, routing, and API compatibility |
| Open WebUI | Provides chat, workspaces, documents, prompts, and browser features |

When startup fails partway through, the control screen stops anything it already started. This prevents hidden model or server processes from being left behind.

Press **Stop complete stack** to shut down the services in the safe reverse order.

## Recommended defaults

The first launch should use the values already shown:

```text
Context size:           16384
Parallel conversations: 1
K cache:                q8_0
V cache:                q4_0
GPU layers:             all
```

These settings aim for a useful balance of memory use, speed, and compatibility. They are not guaranteed to fit every model and computer.

## When to open Advanced model settings

Use the advanced model settings only when:

- the model does not fit in memory;
- the installed llama.cpp build rejects a cache format;
- you need CPU-only operation;
- you understand the hardware-specific values you want.

Common recovery steps:

1. Reduce context size from 16384 to 8192.
2. Try a smaller GGUF model.
3. Change GPU layers from `all` to a smaller number or `0`.
4. Change both cache formats to `f16`.

## Browser workspace settings

The Open WebUI section controls:

- the local browser address;
- where conversations and workspace data are stored;
- whether the browser opens automatically;
- whether local user accounts are enabled.

For one person using one computer, the default local single-user mode is the simplest option. Enable accounts before exposing the interface to any network.

## Advanced proxy

The **Advanced proxy** tab is for people who already have an OpenAI-compatible model server or need custom API values. It starts only the RLM proxy and does not manage a GGUF model or Open WebUI.

Most local users do not need this tab.

## Workspaces

The **Workspaces** tab exposes the underlying slot and workstream catalog. It is useful for deliberate context separation, but normal Open WebUI conversations and workspaces can be used without editing JSON.

## Test request

The test tab sends a direct request through the local RLM proxy and shows routing and usage details. It is primarily a diagnostic tool.

## Monitoring

The monitoring tab shows uptime, completed requests, failures, latency, token totals, workspace counts, and recent request records. It does not retain prompt text, selected context, or generated answers.

## Local-only safety

All services listen only on this computer by default. Do not change the hosts to `0.0.0.0` or expose the ports to a network unless authentication and firewall rules are configured.

## Current limitations

The control screen does not yet download llama.cpp or search Hugging Face for GGUF models. Those two files must currently be downloaded separately. Hardware-aware recommendations and automatic fallback after memory errors are planned follow-on work.
