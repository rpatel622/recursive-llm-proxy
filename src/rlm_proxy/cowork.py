"""Launch the local llama.cpp, RLM proxy, and Open WebUI cowork stack."""

from __future__ import annotations

import argparse
import os
import secrets
import signal
import time

from .managed_llama import LlamaServerLaunchConfig, managed_llama_server
from .managed_proxy import ProxyLaunchConfig, managed_proxy
from .managed_webui import WebUILaunchConfig, managed_webui


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local Recursive LLM cowork stack")
    parser.add_argument("--host", default=os.getenv("RLM_COWORK_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("RLM_COWORK_PORT", "3000")))
    parser.add_argument(
        "--proxy-url", default=os.getenv("RLM_COWORK_PROXY_URL", "http://127.0.0.1:8000")
    )
    parser.add_argument("--api-key", default=os.getenv("RLM_COWORK_PROXY_API_KEY", ""))
    parser.add_argument(
        "--data-dir",
        default=os.getenv("RLM_COWORK_DATA_DIR", "~/.recursive-llm/open-webui"),
    )
    parser.add_argument(
        "--auth",
        action="store_true",
        default=os.getenv("RLM_COWORK_AUTH", "false").lower() in {"1", "true", "yes"},
        help="Enable Open WebUI accounts. The default is local single-user mode.",
    )
    parser.add_argument("--no-browser", action="store_true")

    parser.add_argument(
        "--model",
        default=os.getenv("RLM_COWORK_MODEL", ""),
        help="GGUF model path. When supplied, rlm-cowork starts llama-server and the proxy.",
    )
    parser.add_argument(
        "--llama-binary",
        default=os.getenv("RLM_COWORK_LLAMA_BINARY", "llama-server"),
    )
    parser.add_argument(
        "--llama-host", default=os.getenv("RLM_COWORK_LLAMA_HOST", "127.0.0.1")
    )
    parser.add_argument(
        "--llama-port", type=int, default=int(os.getenv("RLM_COWORK_LLAMA_PORT", "8080"))
    )
    parser.add_argument(
        "--context-size", type=int, default=int(os.getenv("RLM_COWORK_CONTEXT_SIZE", "16384"))
    )
    parser.add_argument(
        "--parallel", type=int, default=int(os.getenv("RLM_COWORK_PARALLEL", "1"))
    )
    parser.add_argument("--cache-type-k", default=os.getenv("RLM_COWORK_CACHE_TYPE_K", "q8_0"))
    parser.add_argument("--cache-type-v", default=os.getenv("RLM_COWORK_CACHE_TYPE_V", "q4_0"))
    parser.add_argument("--gpu-layers", default=os.getenv("RLM_COWORK_GPU_LAYERS", "all"))
    parser.add_argument(
        "--proxy-host", default=os.getenv("RLM_COWORK_PROXY_HOST", "127.0.0.1")
    )
    parser.add_argument(
        "--proxy-port", type=int, default=int(os.getenv("RLM_COWORK_PROXY_PORT", "8000"))
    )
    parser.add_argument(
        "--max-depth", type=int, default=int(os.getenv("RLM_COWORK_MAX_DEPTH", "2"))
    )
    parser.add_argument(
        "--max-iterations", type=int, default=int(os.getenv("RLM_COWORK_MAX_ITERATIONS", "20"))
    )
    args = parser.parse_args()

    started_llama = False
    started_proxy = False
    proxy_url = args.proxy_url
    api_key = args.api_key

    try:
        if args.model:
            llama_config = LlamaServerLaunchConfig(
                model_path=args.model,
                binary=args.llama_binary,
                host=args.llama_host,
                port=args.llama_port,
                context_size=args.context_size,
                parallel=args.parallel,
                cache_type_k=args.cache_type_k,
                cache_type_v=args.cache_type_v,
                gpu_layers=args.gpu_layers,
            )
            llama_status = managed_llama_server.start(llama_config)
            started_llama = True
            print(f"llama-server is running at {llama_status['url']}")

            api_key = api_key or secrets.token_urlsafe(24)
            proxy_config = ProxyLaunchConfig(
                host=args.proxy_host,
                port=args.proxy_port,
                public_api_key=api_key,
                private_api_base=llama_config.url,
                private_api_key="not-needed",
                model="openai/local",
                recursive_model="openai/local",
                max_depth=args.max_depth,
                max_iterations=args.max_iterations,
            )
            proxy_status = managed_proxy.start(proxy_config)
            started_proxy = True
            proxy_url = str(proxy_status["url"])
            print(f"Recursive LLM proxy is running at {proxy_url}")

        config = WebUILaunchConfig(
            host=args.host,
            port=args.port,
            proxy_url=proxy_url,
            proxy_api_key=api_key,
            data_dir=args.data_dir,
            auth_enabled=args.auth,
            open_browser=not args.no_browser,
        )
        status = managed_webui.start(config)
        print(f"Local RLM Cowork is running at {status['url']}")
        print("Press Ctrl+C to stop the managed stack.")

        stopped = False

        def stop_process(*_: object) -> None:
            nonlocal stopped
            if stopped:
                return
            stopped = True
            managed_webui.stop()
            if started_proxy:
                managed_proxy.stop()
            if started_llama:
                managed_llama_server.stop()

        signal.signal(signal.SIGINT, stop_process)
        signal.signal(signal.SIGTERM, stop_process)
        try:
            while not stopped and managed_webui.status().get("running"):
                time.sleep(0.5)
        finally:
            stop_process()
    except Exception:
        managed_webui.stop()
        if started_proxy:
            managed_proxy.stop()
        if started_llama:
            managed_llama_server.stop()
        raise


if __name__ == "__main__":
    main()
