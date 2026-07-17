# Local RLM Cowork

A private AI workspace that runs on your computer and opens in your browser.

Local RLM Cowork combines a GGUF model, llama.cpp, Recursive Language Models, and Open WebUI. Release bundles include the application runtime and model server, so normal installation does not require Python, Command Prompt, PowerShell, Terminal, pip, virtual environments, or API configuration.

## Start

You need only:

1. A Local RLM Cowork release bundle for your operating system.
2. A `.gguf` model that fits your computer.

Download and fully extract one of these release files from the repository's **Releases** page:

- `local-rlm-cowork-windows-x64.zip`
- `local-rlm-cowork-macos-x64.zip`
- `local-rlm-cowork-linux-x64.tar.gz`

The **Continuous build** prerelease is rebuilt automatically from the latest successful `main` commit. Numbered `v*` releases are permanent snapshots intended for normal distribution.

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

## GitHub Packages

The repository also publishes the proxy-only container image to GitHub Container Registry:

```text
ghcr.io/rpatel622/recursive-llm-proxy:latest
```

The container package is for server and developer deployments. Desktop users should download the operating-system bundles from **Releases** instead.

## Repair and updates

Use **Repair installation** in the launcher to reinstall the bundled application from the local wheelhouse without downloading dependencies. Repair preserves models, Open WebUI data, conversations, knowledge collections, and logs.

Release bundles are immutable. To update, download and extract a newer bundle. Persistent user data remains under the normal user-data directory.

## Advanced use

Source installation, CLI startup, OpenAI-compatible API use, context routing, workstreams, and development instructions remain available in the documentation:

- [Bundled installation and release production](docs/bundled-installation.md)
- [Browser cowork interface](docs/cowork.md)
- [Proxy API reference](docs/api.md)
- [Rolling ingestion](docs/rolling-ingestion.md)
- [Slot and workstream routing](docs/slot-routing.md)
- [Architecture](docs/architecture.md)
- [Developer and CLI reference](docs/openai-proxy.md)

## Project status

This is an accessibility-focused local AI project under active development. The application is intended for one trusted local operator. Workspaces and slots organize context; they are not security boundaries.

## Upstream and license

This fork is based on [`grishahq/recursive-llm`](https://github.com/grishahq/recursive-llm), implementing the Recursive Language Models approach described by Alex L. Zhang, Tim Kraska, and Omar Khattab.

- [RLM paper](https://arxiv.org/abs/2512.24601)
- [Official research implementation](https://github.com/alexzhang13/rlm)
- [Upstream Python implementation](https://github.com/grishahq/recursive-llm)

MIT. See [LICENSE](LICENSE).
