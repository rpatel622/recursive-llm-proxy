# Local RLM Cowork

A private AI workspace that runs on your computer and opens in your browser.

Local RLM Cowork combines a GGUF model, llama.cpp, Recursive Language Models, and Open WebUI. Release bundles include the application runtime and model server, so normal installation does not require Python, Command Prompt, PowerShell, Terminal, pip, virtual environments, or API configuration.

## Start

You need only:

1. A Local RLM Cowork release bundle for your operating system.
2. A `.gguf` model that fits your computer.

Download and fully extract one of these release files:

- `local-rlm-cowork-windows-x64.zip`
- `local-rlm-cowork-macos-x64.zip`
- `local-rlm-cowork-linux-x64.tar.gz`

Do not run the launcher from inside the archive.

### Windows

Double-click:

```text
launchers\windows\Start Local RLM Cowork.vbs
```

### macOS

Open:

```text
launchers/macos/Local RLM Cowork.app
```

Development builds are not signed or notarized. macOS may require approval under **System Settings → Privacy & Security**.

### Linux

Double-click:

```text
launchers/linux/Start Local RLM Cowork.desktop
```

Some desktops require **Allow Launching** once.

## First launch

Press **Open Local RLM** in the small launcher window. The bundled application opens the control screen at `http://127.0.0.1:7860`.

In **One-click local stack**:

1. Enter or paste the path to your `.gguf` model.
2. Leave the recommended settings unchanged for the first run.
3. Press **Start complete stack**.

The release already contains a matching `llama-server`; its path is selected automatically and hidden from the normal setup form.

```text
Your browser
  → Open WebUI workspace
  → Local RLM proxy
  → bundled llama-server
  → your GGUF model
```

Default local addresses:

```text
Control screen:  http://127.0.0.1:7860
AI workspace:    http://127.0.0.1:3000
RLM proxy:       http://127.0.0.1:8000
llama-server:    http://127.0.0.1:8080/v1
```

Everything binds to this computer only by default.

## What is bundled

Each platform archive contains:

- A relocatable CPython runtime
- All Python packages required by the proxy, Gradio, and Open WebUI
- A platform-matched llama.cpp release
- An offline wheelhouse for repair
- Native no-terminal launchers
- A manifest recording exact Python, llama.cpp, application, platform, and commit versions

The launcher verifies imports before startup. **Repair installation** reinstalls the application from the local wheelhouse without downloading packages or changing user data.

## What is not bundled

GGUF model weights are not included because they are large and users need different sizes and licenses. Download a model separately and choose it in the control screen.

Current bundles target Windows x64, Linux x64, and macOS x64. Apple Silicon can use the macOS x64 bundle through Rosetta while a native arm64 bundle is being validated.

## Model sizing

Conservative starting points:

| Computer memory | Suggested model |
|---|---|
| 8 GB | 1B–3B, Q4 |
| 16 GB | 3B–8B, Q4 |
| 32 GB | 8B–14B, Q4 or Q5 |
| 64 GB+ | Larger models depending on GPU memory |

Context size, other applications, and GPU memory also affect what will run comfortably.

## Recommended defaults

```text
K cache:       q8_0
V cache:       q4_0
Parallel:      1
GPU layers:    all
Context size:  16384
```

Advanced controls remain available when hardware-specific tuning is needed.

## Large documents and pasted conversations

Open WebUI Knowledge is suited to reusable document collections. Very large one-off messages can be pasted directly into chat. The proxy splits oversized input at natural boundaries, builds semantic metadata, extracts the actual request, and keeps the original text available for targeted inspection.

## Recovery

The launcher writes diagnostics to:

```text
~/.recursive-llm/logs/launcher.log
```

Use these controls without opening a terminal:

- **Repair installation** reinstalls bundled packages from local files.
- **Open diagnostics** opens the log folder.
- **Open browser** reopens the control screen.
- **Stop** stops the launcher-managed control process.

A missing runtime, missing repair wheelhouse, or incomplete archive produces a visible error directing the user to download and fully extract a fresh bundle.

## Source and developer installation

Source checkouts remain supported. When no bundle manifest is present, the graphical launcher creates and manages `~/.recursive-llm/app-venv`, then installs `.[proxy,ui,cowork]`. This fallback requires Python 3.11 or newer.

Advanced documentation:

- [Bundled installation and repair](docs/bundled-installation.md)
- [Browser cowork interface](docs/cowork.md)
- [Proxy API reference](docs/api.md)
- [Rolling ingestion](docs/rolling-ingestion.md)
- [Slot and workstream routing](docs/slot-routing.md)
- [Architecture](docs/architecture.md)
- [Developer and CLI reference](docs/openai-proxy.md)

## Project status

This is an accessibility-focused local AI project under active development. Bundles are produced by GitHub Actions and require native testing before release publication. The application is intended for one trusted local operator. Workspaces organize context; they are not security boundaries.

## Upstream and license

This fork is based on [`grishahq/recursive-llm`](https://github.com/grishahq/recursive-llm), implementing the Recursive Language Models approach described by Alex L. Zhang, Tim Kraska, and Omar Khattab.

- [RLM paper](https://arxiv.org/abs/2512.24601)
- [Official research implementation](https://github.com/alexzhang13/rlm)
- [Upstream Python implementation](https://github.com/grishahq/recursive-llm)

MIT. See [LICENSE](LICENSE).
