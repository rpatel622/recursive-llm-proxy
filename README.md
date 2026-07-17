# Local RLM Cowork

A private AI workspace that runs on your computer and opens in your browser.

This project combines a local GGUF model, llama.cpp, Recursive Language Models, and Open WebUI. It is designed for people who want useful local AI without learning model-server commands, API configuration, or Python environment management.

## What you get

- A familiar browser chat and workspace interface
- Local GGUF model execution through `llama-server`
- Better handling of long documents and very large pasted messages
- Automatic extraction of the real request from large information dumps
- Separate workspaces and conversation context
- A simple control screen for starting and stopping the full local stack
- Advanced API and routing controls when they are actually needed

Your prompts and documents stay on the machine unless you explicitly connect an outside service.

## Start without a terminal

### Before the first launch

You need:

1. **Python 3.11 or newer** from python.org
2. A **llama.cpp `llama-server`** build for your computer
3. A **GGUF model** that fits your available memory
4. This repository downloaded and extracted to a normal folder

The launcher creates its own private Python environment and installs the remaining application components automatically.

### Windows

Double-click:

```text
launchers\windows\Start Local RLM Cowork.vbs
```

No Command Prompt or PowerShell interaction is required.

### macOS

Open:

```text
launchers/macos/Local RLM Cowork.app
```

The app may need approval in **System Settings → Privacy & Security** because development copies are not code-signed.

### Linux

Double-click:

```text
launchers/linux/Start Local RLM Cowork.desktop
```

Some desktop environments require choosing **Allow Launching** once.

## First-time setup in the browser

The launcher opens a small setup window and then the local control page at:

```text
http://127.0.0.1:7860
```

In **One-click local stack**:

1. Choose your `.gguf` model file.
2. Choose the `llama-server` executable, or leave `llama-server` when it is already available to the system.
3. Press **Start complete stack**.
4. Wait for the browser workspace to open.

The normal defaults are already selected:

```text
K cache:       q8_0
V cache:       q4_0
Parallel:      1
GPU layers:    all
Context size:  16384
```

Advanced controls are hidden until you open them.

## What starts

```text
Your browser
  → Open WebUI workspace
  → Local RLM proxy
  → llama-server
  → Your GGUF model
```

Default local addresses:

```text
Control screen:  http://127.0.0.1:7860
AI workspace:    http://127.0.0.1:3000
RLM proxy:       http://127.0.0.1:8000
llama-server:    http://127.0.0.1:8080/v1
```

Everything binds to this computer only by default.

## Large documents and information dumps

When a very large message is pasted directly into chat, the proxy processes it in bounded rolling windows. It looks for headings, paragraphs, lists, and sentence boundaries; creates searchable semantic metadata; extracts the actual request; and keeps the original text available for targeted inspection.

This reduces context-limit failures and avoids repeatedly prefilling the entire dump.

For a reusable document library, use Open WebUI Knowledge. For one-off large pasted content, use normal chat and let rolling ingestion handle it.

## Getting help

The launcher writes setup and startup details to:

```text
~/.recursive-llm/logs/launcher.log
```

Use **Open diagnostics folder** in the launcher window when setup fails.

Common fixes:

- **Python not found:** install Python 3.11+ and reopen the launcher.
- **llama-server not found:** select the executable in the control screen.
- **Model does not start:** try a smaller GGUF model or reduce context size under Advanced model settings.
- **Browser page does not open:** press **Open browser** in the launcher window.

See [No-terminal setup](docs/quickstart.md) for screenshots-ready step-by-step guidance and [Gradio control screen](docs/admin-ui.md) for every visible option.

## For advanced users and developers

The project also exposes an OpenAI-compatible API, context-slot routing, workstreams, metrics, direct Python RLM use, and command-line launchers.

- [Browser cowork interface](docs/cowork.md)
- [Proxy API reference](docs/api.md)
- [Rolling ingestion](docs/rolling-ingestion.md)
- [Slot and workstream routing](docs/slot-routing.md)
- [Architecture](docs/architecture.md)
- [Developer and CLI reference](docs/openai-proxy.md)

## Project status

This is an accessibility-focused local AI project under active development. The double-click launchers remove terminal interaction, but the current release still expects the user to obtain Python, `llama-server`, and a GGUF model separately. Automatic llama.cpp and Hugging Face model downloads are planned follow-on work.

The application is intended for one trusted local operator. Workspaces and slots organize context; they are not security boundaries.

## Upstream and license

This fork is based on [`grishahq/recursive-llm`](https://github.com/grishahq/recursive-llm), implementing the Recursive Language Models approach described by Alex L. Zhang, Tim Kraska, and Omar Khattab.

- [RLM paper](https://arxiv.org/abs/2512.24601)
- [Official research implementation](https://github.com/alexzhang13/rlm)
- [Upstream Python implementation](https://github.com/grishahq/recursive-llm)

MIT. See [LICENSE](LICENSE).
