# One-click local AI roadmap

## Product goal

Make local AI usable without requiring users to understand Python environments, llama.cpp builds, GGUF naming, model-server flags, URLs, ports, or GPU offload.

Target flow:

```text
Launch UI
→ detect platform and hardware
→ install a compatible llama.cpp binary
→ search or choose a GGUF model
→ download with progress and verification
→ start the model server with safe defaults
→ open chat
```

## Baseline llama.cpp defaults

The managed llama.cpp server should begin with:

```text
--cache-type-k q8_0
--cache-type-v q4_0
--parallel 1
--n-gpu-layers all
```

Equivalent short flags:

```text
-ctk q8_0 -ctv q4_0 -np 1 -ngl all
```

These settings belong under Advanced configuration. The primary interface should describe outcomes such as memory use, speed, and quality rather than raw flags.

## Platform policy

Use official `ggml-org/llama.cpp` release binaries rather than compiling locally.

Preferred assets:

- Windows x64: Vulkan build
- Linux x64 or arm64: Vulkan build when Vulkan is available; CPU build fallback
- macOS arm64 or x64: official macOS build using Metal
- unsupported architecture: external-server mode with a plain-language explanation

Do not hard-code one release. Resolve the latest compatible release through the GitHub Releases API, while retaining a configurable pinned known-good version for rollback.

## Safe startup fallbacks

### GPU offload

Start with `-ngl all`. If the process cannot load the model or allocate the KV cache:

1. reduce context size;
2. retry with progressively fewer GPU layers;
3. fall back to CPU offload;
4. recommend a smaller model if loading still fails.

The UI should show one repair action, not raw backend logs.

### KV cache

Start with K=`q8_0`, V=`q4_0`. If the model or backend rejects that combination, retry in this order:

```text
K=q8_0, V=q8_0
K=f16, V=f16
```

Persist and display the effective settings after successful startup.

## Phase 1: llama.cpp release manager

Add a runtime manager that:

- queries official llama.cpp releases;
- maps OS, architecture, and acceleration support to an asset pattern;
- downloads into an application-managed directory;
- verifies SHA-256 when release metadata supplies it;
- safely extracts ZIP and tar archives;
- locates `llama-server` or `llama-server.exe`;
- records release tag, asset name, checksum, and path;
- supports update, reinstall, rollback, and offline reuse;
- never replaces a running backend binary.

Suggested storage:

```text
~/.recursive-llm-proxy/
  runtimes/llama.cpp/<tag>/<platform>/
  models/
  downloads/
  state.sqlite3
  logs/
```

## Phase 2: Hugging Face GGUF search

Use `huggingface_hub.HfApi` or the Hub API to search model repositories.

Search behavior:

- require at least one `.gguf` file;
- support free-text search;
- sort by relevance, downloads, or recent update;
- show author, license, parameter count when available, downloads, update date, file sizes, and quantization;
- hide gated or private models unless a Hugging Face token is configured;
- prefer single-file GGUF models in the simple path;
- support split GGUF only after multipart download and validation are implemented;
- cache results briefly to reduce API requests.

Translate common quantizations into plain-language labels:

```text
Q4_K_M — Recommended balance
Q5_K_M — Better quality, more memory
Q8_0   — Highest practical quality, large
```

Display license and model-card warnings before download.

## Phase 3: model download manager

Add:

- resumable downloads;
- disk-space preflight;
- progress, speed, and remaining-size display;
- cancellation and retry;
- optional Hugging Face token stored in the OS credential store;
- checksum validation when available;
- incomplete and corrupt-file detection;
- delete and relocate actions;
- model inventory with actual disk usage.

## Phase 4: managed llama-server

Generate a command similar to:

```bash
llama-server \
  --model <selected.gguf> \
  --host 127.0.0.1 \
  --port <auto-selected-port> \
  --cache-type-k q8_0 \
  --cache-type-v q4_0 \
  --parallel 1 \
  --n-gpu-layers all \
  --metrics
```

Choose a conservative context size from model metadata and available memory.

Readiness flow:

1. launch the process;
2. stream logs into a bounded redacted buffer;
3. poll the health or model endpoint;
4. classify startup failures;
5. apply safe retries;
6. connect the RLM proxy automatically;
7. persist the working configuration.

The effective command is visible under Diagnostics, not on the main setup screen.

## Phase 5: first-run wizard

Primary steps:

1. **Check this computer**
   - operating system, architecture, RAM, acceleration support, and free disk.
2. **Install model engine**
   - select the recommended official release asset automatically.
3. **Choose a model**
   - show curated recommendations first and Hugging Face search second.
4. **Download**
   - show progress and storage impact.
5. **Start local AI**
   - launch llama.cpp and the proxy with automatic recovery.
6. **Chat**

URLs, ports, API keys, cache types, GPU layers, context size, and parallelism remain under Advanced settings.

## Phase 6: recovery and accessibility

Every common failure gets one primary repair action:

| Failure | Primary action |
|---|---|
| Vulkan unavailable | Use CPU mode |
| Unsupported release asset | Use external model server |
| Insufficient memory | Reduce context and retry |
| Model remains too large | Choose smaller model |
| Insufficient disk | Choose another folder |
| Occupied port | Choose another automatically |
| Corrupt download | Redownload file |
| Gated model | Sign in to Hugging Face |
| Backend crash | Restart with safe settings |

Diagnostics exports must exclude prompts, document contents, API keys, and Hugging Face tokens.

## Acceptance criteria

- A Windows or Linux user with Vulkan support can install an official llama.cpp binary, find and download a GGUF, and reach a working chat without a terminal.
- A macOS user receives the official Metal-capable macOS build automatically.
- Default launch uses `ctk=q8_0`, `ctv=q4_0`, `parallel=1`, and full GPU offload.
- Startup automatically recovers from unsupported KV types, insufficient VRAM, and occupied ports.
- Executables and models are stored outside the repository checkout.
- Existing external-server and manual advanced configuration remain supported.
- Tests cover asset selection, release parsing, safe extraction, GGUF filtering, command generation, fallback order, and secret/content redaction.

## Suggested pull request sequence

1. Release and asset resolver plus runtime installer
2. Hugging Face GGUF search and model inventory
3. Resumable model download manager
4. Managed llama-server process and fallback policy
5. First-run wizard and chat-first UI
6. Standalone packaging and signed desktop installers
