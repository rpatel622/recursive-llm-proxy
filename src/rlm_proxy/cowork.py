"""Launch a batteries-included Open WebUI interface against the local RLM proxy."""

from __future__ import annotations

import argparse
import os
import signal
import time

from .managed_webui import WebUILaunchConfig, managed_webui


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Open WebUI against recursive-llm-proxy")
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
    args = parser.parse_args()

    config = WebUILaunchConfig(
        host=args.host,
        port=args.port,
        proxy_url=args.proxy_url,
        proxy_api_key=args.api_key,
        data_dir=args.data_dir,
        auth_enabled=args.auth,
        open_browser=not args.no_browser,
    )
    status = managed_webui.start(config)
    print(f"Local RLM Cowork is running at {status['url']}")
    print("Press Ctrl+C to stop it.")

    stopped = False

    def stop_process(*_: object) -> None:
        nonlocal stopped
        if not stopped:
            stopped = True
            managed_webui.stop()

    signal.signal(signal.SIGINT, stop_process)
    signal.signal(signal.SIGTERM, stop_process)
    try:
        while not stopped and managed_webui.status().get("running"):
            time.sleep(0.5)
    finally:
        stop_process()


if __name__ == "__main__":
    main()
