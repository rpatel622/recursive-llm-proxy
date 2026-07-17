"""Gradio helpers for managing llama.cpp, the proxy, and Open WebUI."""

from __future__ import annotations

import os
from typing import Any, Dict, Tuple

from .managed_llama import LlamaServerLaunchConfig, managed_llama_server
from .managed_proxy import ProxyLaunchConfig, managed_proxy
from .managed_webui import WebUILaunchConfig, managed_webui


def default_llama_binary() -> str:
    """Prefer the release-bundled llama-server while preserving source installs."""
    return os.getenv("RLM_BUNDLED_LLAMA_SERVER", "llama-server")


def stack_status() -> Dict[str, Any]:
    return {
        "llama_server": managed_llama_server.status(),
        "proxy": managed_proxy.status(),
        "open_webui": managed_webui.status(),
    }


def start_complete_stack(
    llama_binary: str,
    model_path: str,
    llama_host: str,
    llama_port: float,
    context_size: float,
    parallel: float,
    cache_type_k: str,
    cache_type_v: str,
    gpu_layers: str,
    proxy_host: str,
    proxy_port: float,
    public_api_key: str,
    max_depth: float,
    max_iterations: float,
    webui_host: str,
    webui_port: float,
    data_dir: str,
    auth_enabled: bool,
    open_browser: bool,
) -> Tuple[str, str, str, str, Dict[str, Any]]:
    llama_config = LlamaServerLaunchConfig(
        binary=llama_binary.strip() or default_llama_binary(),
        model_path=model_path.strip(),
        host=llama_host.strip(),
        port=int(llama_port),
        context_size=int(context_size),
        parallel=int(parallel),
        cache_type_k=cache_type_k.strip(),
        cache_type_v=cache_type_v.strip(),
        gpu_layers=gpu_layers.strip(),
    )
    proxy_config = ProxyLaunchConfig(
        host=proxy_host.strip(),
        port=int(proxy_port),
        public_api_key=public_api_key.strip(),
        private_api_base=llama_config.url,
        private_api_key="not-needed",
        model="openai/local",
        recursive_model="openai/local",
        max_depth=int(max_depth),
        max_iterations=int(max_iterations),
    )
    webui_config = WebUILaunchConfig(
        host=webui_host.strip(),
        port=int(webui_port),
        proxy_url=proxy_config.url,
        proxy_api_key=proxy_config.public_api_key,
        data_dir=data_dir.strip(),
        auth_enabled=auth_enabled,
        open_browser=open_browser,
    )

    try:
        managed_webui.stop()
        managed_proxy.stop()
        managed_llama_server.stop()
        managed_llama_server.start(llama_config)
        managed_proxy.start(proxy_config)
        managed_webui.start(webui_config)
        return (
            f"Complete local stack is running. Open {webui_config.url}",
            proxy_config.url,
            proxy_config.public_api_key,
            webui_config.url,
            stack_status(),
        )
    except Exception as exc:
        managed_webui.stop()
        managed_proxy.stop()
        managed_llama_server.stop()
        return (
            f"Stack startup failed: {exc}",
            proxy_config.url,
            proxy_config.public_api_key,
            webui_config.url,
            stack_status(),
        )


def stop_complete_stack() -> Tuple[str, Dict[str, Any]]:
    errors = []
    for name, manager in (
        ("Open WebUI", managed_webui),
        ("proxy", managed_proxy),
        ("llama-server", managed_llama_server),
    ):
        try:
            manager.stop()
        except Exception as exc:  # pragma: no cover
            errors.append(f"{name}: {exc}")
    if errors:
        return "Stack stopped with errors: " + "; ".join(errors), stack_status()
    return "Complete local stack stopped", stack_status()


def refresh_stack_status() -> Tuple[str, Dict[str, Any]]:
    details = stack_status()
    running = [name for name, value in details.items() if value.get("running")]
    if len(running) == 3:
        message = "All local services are running"
    elif running:
        message = "Running: " + ", ".join(running)
    else:
        message = "No managed local services are running"
    return message, details


def build_stack_tab(gr: Any, proxy_url: Any, api_key: Any) -> None:
    with gr.Tab("One-click local stack"):
        bundled = os.getenv("RLM_BUNDLED_LLAMA_SERVER")
        if bundled:
            gr.Markdown(
                "Choose a GGUF model and press **Start complete stack**. llama.cpp is included "
                "in this release bundle."
            )
        else:
            gr.Markdown(
                "Choose a GGUF model and press **Start complete stack**. The UI starts "
                "llama-server, the RLM proxy, and Open WebUI in the correct order."
            )
        with gr.Row():
            model_path = gr.Textbox(
                label="GGUF model file",
                placeholder="C:\\Models\\model.gguf or /path/to/model.gguf",
                scale=2,
            )
            llama_binary = gr.Textbox(
                label="llama-server binary",
                value=default_llama_binary(),
                scale=1,
                visible=not bool(bundled),
            )
        with gr.Accordion("llama.cpp settings", open=False):
            with gr.Row():
                llama_host = gr.Textbox(label="llama-server host", value="127.0.0.1")
                llama_port = gr.Number(label="llama-server port", value=8080, precision=0)
                context_size = gr.Number(label="Context size", value=16384, precision=0)
                parallel = gr.Number(label="Parallel slots", value=1, precision=0)
            with gr.Row():
                cache_type_k = gr.Dropdown(
                    label="K cache type", choices=["q8_0", "q4_0", "f16"], value="q8_0"
                )
                cache_type_v = gr.Dropdown(
                    label="V cache type", choices=["q4_0", "q8_0", "f16"], value="q4_0"
                )
                gpu_layers = gr.Textbox(label="GPU layers", value="all")
        with gr.Accordion("Proxy settings", open=False):
            with gr.Row():
                proxy_host = gr.Textbox(label="Proxy host", value="127.0.0.1")
                proxy_port = gr.Number(label="Proxy port", value=8000, precision=0)
                public_api_key = gr.Textbox(label="Public API key", type="password")
            with gr.Row():
                max_depth = gr.Number(label="Maximum RLM depth", value=2, precision=0)
                max_iterations = gr.Number(label="Maximum RLM iterations", value=20, precision=0)
        with gr.Accordion("Browser interface settings", open=False):
            with gr.Row():
                webui_host = gr.Textbox(label="Open WebUI host", value="127.0.0.1")
                webui_port = gr.Number(label="Open WebUI port", value=3000, precision=0)
                data_dir = gr.Textbox(
                    label="Persistent data directory", value="~/.recursive-llm/open-webui"
                )
            with gr.Row():
                auth_enabled = gr.Checkbox(label="Enable Open WebUI accounts", value=False)
                open_browser = gr.Checkbox(label="Open browser after startup", value=True)
        with gr.Row():
            start_stack = gr.Button("Start complete stack", variant="primary")
            stop_stack = gr.Button("Stop complete stack")
            refresh_stack = gr.Button("Refresh stack status")
        stack_message = gr.Textbox(label="Stack status", interactive=False)
        webui_url = gr.Textbox(label="Open WebUI URL", interactive=False)
        stack_details = gr.JSON(label="Service details")

        start_stack.click(
            start_complete_stack,
            inputs=[
                llama_binary,
                model_path,
                llama_host,
                llama_port,
                context_size,
                parallel,
                cache_type_k,
                cache_type_v,
                gpu_layers,
                proxy_host,
                proxy_port,
                public_api_key,
                max_depth,
                max_iterations,
                webui_host,
                webui_port,
                data_dir,
                auth_enabled,
                open_browser,
            ],
            outputs=[stack_message, proxy_url, api_key, webui_url, stack_details],
        )
        stop_stack.click(stop_complete_stack, outputs=[stack_message, stack_details])
        refresh_stack.click(refresh_stack_status, outputs=[stack_message, stack_details])
