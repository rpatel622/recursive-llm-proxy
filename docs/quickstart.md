# Start Local RLM Cowork without a terminal

This guide is for people who want a private AI workspace in the browser without using Command Prompt, PowerShell, Terminal, shell commands, API keys, or environment variables.

## What you need

Before opening the launcher, download these four things:

1. **Python 3.11 or newer** from python.org
2. A **llama.cpp release** containing `llama-server`
3. One **GGUF model** that fits your computer
4. This repository as a ZIP file, extracted to a normal folder

Python is used only as the local application runtime. The launcher creates a separate private environment under your user folder and installs the application there.

## Choose a model that fits

GGUF files can be several gigabytes. As a conservative starting point:

| Computer memory | Suggested starting size |
|---|---|
| 8 GB RAM | Small 1B–3B model, Q4 quantization |
| 16 GB RAM | 3B–8B model, Q4 quantization |
| 32 GB RAM | 8B–14B model, Q4 or Q5 quantization |
| 64 GB+ RAM | Larger models, depending on GPU memory |

These are rough starting points. Other applications, context size, and GPU memory affect what will run comfortably.

## Windows

1. Open the extracted repository folder.
2. Open `launchers`, then `windows`.
3. Double-click **Start Local RLM Cowork.vbs**.
4. In the small launcher window, press **Set up and open**.
5. Wait while the private app environment is prepared.

The launcher works in the background and does not require Command Prompt or PowerShell interaction.

## macOS

1. Open the extracted repository folder.
2. Open `launchers`, then `macos`.
3. Double-click **Local RLM Cowork.app**.
4. Press **Set up and open**.

Because development copies are not signed, macOS may block the first launch. Open **System Settings → Privacy & Security**, approve the app, and try again.

## Linux

1. Open the extracted repository folder.
2. Open `launchers`, then `linux`.
3. Double-click **Start Local RLM Cowork.desktop**.
4. Choose **Allow Launching** when your desktop asks.
5. Press **Set up and open**.

Desktop behavior differs between distributions. Python 3.11+ and Tk support must be installed through the normal software center or package manager.

## Configure the local model

The launcher opens the control screen in your browser.

Under **One-click local stack**:

1. Enter or paste the path to your GGUF file.
2. Enter the path to `llama-server` when it is not already available as `llama-server`.
3. Leave the recommended settings unchanged for the first launch.
4. Press **Start complete stack**.

The status panel shows each service:

```text
llama-server → RLM proxy → Open WebUI
```

When all three are running, Open WebUI opens automatically at `http://127.0.0.1:3000`.

## Recommended first-run settings

The defaults favor compatibility and predictable local use:

| Setting | Default | Purpose |
|---|---:|---|
| Context size | 16384 | Amount of active text the model can consider |
| Parallel conversations | 1 | Reduces memory use and avoids competing generations |
| K cache | q8_0 | Keeps attention-cache quality relatively high |
| V cache | q4_0 | Reduces memory use |
| GPU layers | all | Tries to use available GPU acceleration |

Open **Advanced model settings** only when the model fails to start or you know the hardware-specific values you want.

## Use the browser workspace

Open WebUI provides normal conversations, workspaces, document knowledge, saved prompts, and other browser features.

For large content:

- Add documents to **Knowledge** when they should remain available across conversations.
- Paste one-off large text directly into chat. The proxy automatically splits and preprocesses oversized messages before answering.

## Stop the application

Return to the launcher window and press **Stop**. This stops the Gradio control screen. Use **Stop complete stack** in the control screen first when llama-server, the proxy, and Open WebUI are running.

## Troubleshooting without a terminal

Press **Open diagnostics folder** in the launcher window. The main log is:

```text
~/.recursive-llm/logs/launcher.log
```

### Python was not found

Install Python 3.11 or newer from python.org. On Windows, include the Python launcher during installation.

### Setup could not finish

Check that the computer has internet access and enough free disk space. Open the diagnostics folder for the installer output.

### llama-server was not found

In the control screen, provide the full path to the executable from the extracted llama.cpp release.

### The model stopped during startup

Try these in order:

1. Reduce context size to 8192.
2. Use a smaller GGUF model.
3. Change GPU layers from `all` to a smaller number or `0` for CPU-only use.
4. Change cache types to `f16` if the installed llama.cpp build rejects quantized cache settings.

### The browser did not open

Press **Open browser** in the launcher window, or visit `http://127.0.0.1:7860` manually.

## Advanced and developer setup

Command-line startup, OpenAI-compatible API use, slot routing, and direct Python examples remain available in:

- [Developer and CLI reference](openai-proxy.md)
- [Proxy API reference](api.md)
- [Slot routing](slot-routing.md)
- [Architecture](architecture.md)
