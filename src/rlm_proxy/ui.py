"""Gradio administration UI for the local RLM stack."""

from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict, List, Optional, Tuple

from .managed_proxy import ProxyLaunchConfig, managed_proxy
from .stack_ui import build_stack_tab


def _headers(api_key: str) -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key.strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"
    return headers


def _base_url(value: str) -> str:
    url = value.strip().rstrip("/")
    if not url.startswith(("http://", "https://")):
        raise ValueError("Proxy URL must begin with http:// or https://")
    return url


def _request(
    method: str,
    proxy_url: str,
    api_key: str,
    path: str,
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    import httpx

    with httpx.Client(timeout=30.0) as client:
        response = client.request(
            method,
            f"{_base_url(proxy_url)}{path}",
            headers=_headers(api_key),
            json=payload,
        )
    try:
        body: Any = response.json()
    except ValueError:
        body = {"text": response.text}
    if response.is_error:
        raise RuntimeError(f"HTTP {response.status_code}: {json.dumps(body, ensure_ascii=False)}")
    return body if isinstance(body, dict) else {"data": body}


def start_local_proxy(
    host: str,
    port: float,
    public_api_key: str,
    private_api_base: str,
    private_api_key: str,
    model: str,
    recursive_model: str,
    max_depth: float,
    max_iterations: float,
) -> Tuple[str, str, str, Dict[str, Any]]:
    try:
        config = ProxyLaunchConfig(
            host=host.strip(),
            port=int(port),
            public_api_key=public_api_key.strip(),
            private_api_base=private_api_base.strip(),
            private_api_key=private_api_key.strip(),
            model=model.strip(),
            recursive_model=recursive_model.strip(),
            max_depth=int(max_depth),
            max_iterations=int(max_iterations),
        )
        status = managed_proxy.start(config)
        return f"Proxy running at {config.url}", config.url, config.public_api_key, status
    except Exception as exc:
        return f"Proxy start failed: {exc}", "", public_api_key, managed_proxy.status()


def stop_local_proxy() -> Tuple[str, Dict[str, Any]]:
    try:
        return "Proxy stopped", managed_proxy.stop()
    except Exception as exc:
        return f"Proxy stop failed: {exc}", managed_proxy.status()


def local_proxy_status() -> Tuple[str, Dict[str, Any]]:
    status = managed_proxy.status()
    return (
        "Proxy is running" if status.get("running") else "Proxy is not running",
        status,
    )


def connection_status(proxy_url: str, api_key: str) -> Tuple[str, Dict[str, Any]]:
    try:
        return "Connected", {
            "health": _request("GET", proxy_url, api_key, "/healthz"),
            "models": _request("GET", proxy_url, api_key, "/v1/models"),
        }
    except Exception as exc:
        return f"Connection failed: {exc}", {}


def load_catalog(proxy_url: str, api_key: str) -> Tuple[str, str]:
    try:
        catalog = _request("GET", proxy_url, api_key, "/v1/rlm/slots")
        return "Catalog loaded", json.dumps(catalog, ensure_ascii=False, indent=2)
    except Exception as exc:
        return f"Load failed: {exc}", ""


def save_catalog(proxy_url: str, api_key: str, catalog_text: str) -> Tuple[str, str]:
    try:
        payload = json.loads(catalog_text)
        if not isinstance(payload, dict):
            raise ValueError("Catalog must be a JSON object")
        result = _request("PUT", proxy_url, api_key, "/v1/rlm/slots", payload)
        return "Catalog saved", json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as exc:
        return f"Save failed: {exc}", catalog_text


def _workstream_slugs(value: str) -> List[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def run_test_request(
    proxy_url: str,
    api_key: str,
    query: str,
    routing_mode: str,
    slot_slug: str,
    workstream_slugs: str,
    initial_turn_count: float,
    max_turn_count: float,
    allow_multi_workstream: bool,
    allow_cross_slot: bool,
) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
    try:
        routing: Dict[str, Any] = {
            "mode": routing_mode,
            "initial_turn_count": int(initial_turn_count),
            "max_turn_count": int(max_turn_count),
            "allow_multi_workstream": allow_multi_workstream,
            "allow_cross_slot": allow_cross_slot,
        }
        if slot_slug.strip():
            routing["slot_slug"] = slot_slug.strip()
        selected = _workstream_slugs(workstream_slugs)
        if selected:
            routing["workstream_slugs"] = selected
        response = _request(
            "POST",
            proxy_url,
            api_key,
            "/v1/chat/completions",
            {
                "model": "rlm",
                "messages": [{"role": "user", "content": query}],
                "rlm": {"routing": routing},
            },
        )
        choices = response.get("choices") or []
        answer = ""
        if choices and isinstance(choices[0], dict):
            answer = str((choices[0].get("message") or {}).get("content") or "")
        metadata = response.get("rlm") or {}
        return answer, metadata.get("routing") or {}, metadata.get("stats") or {}
    except Exception as exc:
        return f"Request failed: {exc}", {}, {}


def refresh_monitor(proxy_url: str, api_key: str) -> Tuple[str, Dict[str, Any]]:
    try:
        snapshot = _request("GET", proxy_url, api_key, "/v1/rlm/metrics")
        summary = (
            f"**Uptime:** {snapshot.get('uptime_seconds', 0)} s  \n"
            f"**Requests:** {snapshot.get('total_requests', 0)} total, "
            f"{snapshot.get('successful_requests', 0)} successful, "
            f"{snapshot.get('failed_requests', 0)} failed  \n"
            f"**Average latency:** {snapshot.get('average_latency_ms', 0)} ms  \n"
            f"**Tokens:** {snapshot.get('total_tokens', 0)}  \n"
            f"**Catalog:** {snapshot.get('slot_count', 0)} slots, "
            f"{snapshot.get('workstream_count', 0)} workstreams"
        )
        return summary, snapshot
    except Exception as exc:
        return f"Monitoring failed: {exc}", {}


def build_ui(
    default_proxy_url: str = "http://127.0.0.1:8000",
    default_api_key: str = "",
) -> Any:
    import gradio as gr

    with gr.Blocks(title="Local RLM") as demo:
        gr.Markdown("# Local RLM")
        gr.Markdown(
            "Use **One-click local stack** for normal setup. Advanced tabs remain available "
            "for custom servers, routing, and diagnostics."
        )

        with gr.Row():
            proxy_url = gr.Textbox(label="Active proxy URL", value=default_proxy_url)
            api_key = gr.Textbox(
                label="Active proxy API key", value=default_api_key, type="password"
            )
            check_button = gr.Button("Check connection")
        connection_message = gr.Textbox(label="Connection status", interactive=False)
        connection_details = gr.JSON(label="Connection details")
        check_button.click(
            connection_status,
            inputs=[proxy_url, api_key],
            outputs=[connection_message, connection_details],
        )

        build_stack_tab(gr, proxy_url, api_key)

        with gr.Tab("Advanced proxy"):
            gr.Markdown("Connect the proxy to any existing OpenAI-compatible model endpoint.")
            with gr.Row():
                proxy_host = gr.Textbox(label="Proxy bind host", value="127.0.0.1")
                proxy_port = gr.Number(label="Proxy port", value=8000, precision=0)
                public_api_key = gr.Textbox(label="Public API key", type="password")
            with gr.Row():
                private_api_base = gr.Textbox(
                    label="Private API base", value="http://127.0.0.1:8080/v1"
                )
                private_api_key = gr.Textbox(
                    label="Private API key", value="not-needed", type="password"
                )
            with gr.Row():
                model = gr.Textbox(label="Root model", value="openai/local")
                recursive_model = gr.Textbox(label="Recursive model", value="openai/local")
                max_depth = gr.Number(label="Maximum depth", value=2, precision=0)
                max_iterations = gr.Number(label="Maximum iterations", value=20, precision=0)
            with gr.Row():
                start_button = gr.Button("Start / restart proxy", variant="primary")
                stop_button = gr.Button("Stop proxy")
                status_button = gr.Button("Refresh proxy status")
            process_message = gr.Textbox(label="Proxy process status", interactive=False)
            process_details = gr.JSON(label="Proxy process details")
            start_button.click(
                start_local_proxy,
                inputs=[
                    proxy_host,
                    proxy_port,
                    public_api_key,
                    private_api_base,
                    private_api_key,
                    model,
                    recursive_model,
                    max_depth,
                    max_iterations,
                ],
                outputs=[process_message, proxy_url, api_key, process_details],
            )
            stop_button.click(stop_local_proxy, outputs=[process_message, process_details])
            status_button.click(local_proxy_status, outputs=[process_message, process_details])

        with gr.Tab("Workspaces"):
            gr.Markdown("Advanced slot/workstream catalog editor.")
            catalog_status = gr.Textbox(label="Status", interactive=False)
            catalog = gr.Code(label="Catalog JSON", language="json", lines=24)
            with gr.Row():
                load_button = gr.Button("Load catalog")
                save_button = gr.Button("Validate and replace", variant="primary")
            load_button.click(
                load_catalog,
                inputs=[proxy_url, api_key],
                outputs=[catalog_status, catalog],
            )
            save_button.click(
                save_catalog,
                inputs=[proxy_url, api_key, catalog],
                outputs=[catalog_status, catalog],
            )

        with gr.Tab("Test request"):
            query = gr.Textbox(label="User request", lines=5)
            with gr.Row():
                routing_mode = gr.Dropdown(
                    choices=["auto", "explicit", "clarify_only"],
                    value="auto",
                    label="Routing mode",
                )
                slot_slug = gr.Textbox(label="Workspace slug")
                workstream_slugs = gr.Textbox(
                    label="Conversation/workstream slugs", placeholder="comma,separated"
                )
            with gr.Row():
                initial_turn_count = gr.Number(label="Initial turns", value=4, precision=0)
                max_turn_count = gr.Number(label="Maximum turns", value=64, precision=0)
                allow_multi = gr.Checkbox(label="Allow multiple workstreams", value=True)
                allow_cross = gr.Checkbox(label="Allow cross-workspace routing", value=False)
            run_button = gr.Button("Run request", variant="primary")
            answer = gr.Textbox(label="Assistant response", lines=10)
            with gr.Row():
                routing_result = gr.JSON(label="Routing")
                stats_result = gr.JSON(label="RLM statistics")
            run_button.click(
                run_test_request,
                inputs=[
                    proxy_url,
                    api_key,
                    query,
                    routing_mode,
                    slot_slug,
                    workstream_slugs,
                    initial_turn_count,
                    max_turn_count,
                    allow_multi,
                    allow_cross,
                ],
                outputs=[answer, routing_result, stats_result],
            )

        with gr.Tab("Monitoring"):
            refresh_button = gr.Button("Refresh metrics", variant="primary")
            monitor_summary = gr.Markdown()
            monitor_data = gr.JSON(label="Metrics and recent requests")
            refresh_button.click(
                refresh_monitor,
                inputs=[proxy_url, api_key],
                outputs=[monitor_summary, monitor_data],
            )

    return demo


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Local RLM Gradio interface")
    parser.add_argument("--host", default=os.getenv("RLM_PROXY_UI_HOST", "127.0.0.1"))
    parser.add_argument("--port", default=int(os.getenv("RLM_PROXY_UI_PORT", "7860")), type=int)
    parser.add_argument(
        "--proxy-url", default=os.getenv("RLM_PROXY_UI_PROXY_URL", "http://127.0.0.1:8000")
    )
    parser.add_argument("--api-key", default=os.getenv("RLM_PROXY_UI_API_KEY", ""))
    args = parser.parse_args()
    build_ui(args.proxy_url, args.api_key).launch(
        server_name=args.host,
        server_port=args.port,
        show_error=True,
    )


if __name__ == "__main__":
    main()
