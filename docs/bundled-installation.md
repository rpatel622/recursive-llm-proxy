# Bundled installation and repair

Release bundles are the normal installation path for Local RLM Cowork. They are designed for people who do not want to install Python, use a terminal, manage packages, or locate a separate llama.cpp build.

## Install

1. Download the archive for your operating system from the GitHub release.
2. Extract the entire archive to a normal folder you can keep.
3. Open the platform launcher.
4. Press **Open Local RLM**.
5. Choose a GGUF model in the browser control screen.
6. Press **Start complete stack**.

Do not move individual launcher files out of the extracted folder. The launcher, runtime, wheelhouse, and llama.cpp files use relative paths within the bundle.

## Bundle layout

```text
local-rlm-cowork/
  bundle-manifest.json
  launchers/
    launcher.pyw
    windows/
    macos/
    linux/
  runtime/
    python/
    llama/
    wheelhouse/
    python-release.json
    llama-release.json
  docs/
```

`bundle-manifest.json` records the application commit, target platform, Python runtime release, exact Python asset, llama.cpp release, and exact llama.cpp asset.

## Startup checks

Before starting the control screen, the launcher verifies that the bundled runtime can import:

- `rlm_proxy`
- Gradio
- Open WebUI

The launcher also locates the bundled `llama-server` and passes its absolute path into the Gradio process. The normal setup form therefore does not ask bundled users to find the server executable.

## Offline repair

Every release includes the wheels used to build that release. Press **Repair installation** to force-reinstall the application and all declared extras from those local files.

Repair does not:

- download packages
- replace GGUF models
- delete Open WebUI data
- delete conversation history
- delete launcher logs

Repair fails visibly when the wheelhouse or runtime is missing. In that case, download and fully extract a fresh release bundle.

## Updating

Release bundles are immutable. To update:

1. Stop the complete stack and launcher.
2. Download and extract the newer release into a new folder.
3. Open the new launcher.

Persistent Open WebUI data remains under `~/.recursive-llm/open-webui` by default, so replacing the application folder does not remove conversations or knowledge collections.

## Source fallback

The source-code checkout still supports a managed virtual environment for contributors and advanced users. When `bundle-manifest.json` and `runtime/python` are absent, `launcher.pyw` creates `~/.recursive-llm/app-venv` and installs the current checkout.

Source fallback requires Python 3.11 or newer and internet access for the initial installation. It is not the recommended end-user distribution.

## Release production

The `Build fully bundled Local RLM releases` workflow:

1. downloads a relocatable CPython runtime from `astral-sh/python-build-standalone`
2. downloads a platform-matched llama.cpp release from `ggml-org/llama.cpp`
3. builds a complete offline wheelhouse for the project extras
4. installs those wheels into the bundled runtime
5. verifies Tk, Gradio, Open WebUI, and `rlm_proxy` imports
6. verifies that `llama-server` exists
7. writes the version manifest
8. packages platform artifacts
9. uploads artifacts for pull requests and workflow dispatches
10. attaches artifacts to GitHub releases for version tags

The workflow currently builds Windows x64, Linux x64, and macOS x64 artifacts. Native platform smoke testing remains required before publishing a release.
