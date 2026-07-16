"""Simple Gradio administration UI for proxy configuration and monitoring."""

from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict, List, Optional, Tuple


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

    url = f"{_base_url(proxy_url)}{path}"
    with httpx.Client(timeout=30.0) as client:
        response = client.request(
            method,
            url,
            headers=_headers(api_key),
            json=payload,
        )
    try:
        body: Any = response.json()
    except ValueError:
        body = {"text": response.text}
    if response.is_error:
        raise RuntimeError(f"HTTP {response.status_code}: {json.dumps(body, ensure_ascii=False)}")
    if not isinstance(body, dict):
        return {"data": body}
    return body


def connection_status(proxy_url: str, api_key: str) -> Tuple[str, Dict[str, Any]]:
    try:
        health = _request("GET", proxy_url, api_key, "/healthz")
        models = _request("GET", proxy_url, api_key, "/v1/models")
        return "Connected", {"health": health, "models": models}
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
        payload = {
            "model": "rlm",
            "messages": [{"role": "user", "content": query}],
            "rlm": {"routing": routing},
        }
        response = _request("POST", proxy_url, api_key, "/v1/chat/completions", payload)
        choices = response.get("choices") or []
        answer = ""
        if choices and isinstance(choices[0], dict):
            message = choices[0].get("message") or {}
            answer = str(message.get("content") or "")
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
            f"{snapshot.get('failed_requests', 0)} failed, "
            f"{snapshot.get('clarifications', 0)} clarifications  \n"
            f"**Average latency:** {snapshot.get('average_latency_ms', 0)} ms  \n"
            f"**Tokens:** {snapshot.get('total_tokens', 0)}  \n"
            f"**Catalog:** {snapshot.get('slot_count', 0)} slots, "
            f"{snapshot.get('workstream_count', 0)} workstreams"
        )
        return summary, snapshot
    except Exception as exc:
        return f"Monitoring failed: {exc}", {}


def build_ui(default_proxy_url: str, default_api_key: str) -> Any:
    import gradio as gr

    with gr.Blocks(title="recursive-llm proxy admin") as demo:
        gr.Markdown("# recursive-llm proxy admin")
        with gr.Row():
            proxy_url = gr.Textbox(label="Proxy URL", value=default_proxy_url)
            api_key = gr.Textbox(label="Public API key", value=default_api_key, type="password")
        with gr.Row():
            check_button = gr.Button("Check connection", variant="primary")
            connection_message = gr.Textbox(label="Connection status", interactive=False)
        connection_details = gr.JSON(label="Connection details")
        check_button.click(
            connection_status,
            inputs=[proxy_url, api_key],
            outputs=[connection_message, connection_details],
        )

        with gr.Tab("Slot catalog"):
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
            query = gr.Textbox(label="User query", lines=4)
            with gr.Row():
                routing_mode = gr.Dropdown(
                    choices=["auto", "explicit", "clarify_only"],
                    value="auto",
                    label="Routing mode",
                )
                slot_slug = gr.Textbox(label="Slot slug")
                workstream_slugs = gr.Textbox(
                    label="Workstream slugs", placeholder="comma,separated"
                )
            with gr.Row():
                initial_turn_count = gr.Number(label="Initial turns", value=4, precision=0)
                max_turn_count = gr.Number(label="Maximum turns", value=64, precision=0)
                allow_multi = gr.Checkbox(label="Allow multiple workstreams", value=True)
                allow_cross = gr.Checkbox(label="Allow cross-slot routing", value=False)
            run_button = gr.Button("Run routed request", variant="primary")
            answer = gr.Textbox(label="Assistant response", lines=8)
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
    parser = argparse.ArgumentParser(description="Run the recursive-llm proxy Gradio admin UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=7860, type=int)
    parser.add_argument(
        "--proxy-url",
        default=os.getenv("RLM_PROXY_UI_PROXY_URL", "http://127.0.0.1:8000"),
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("RLM_PROXY_UI_API_KEY", ""),
    )
    args = parser.parse_args()
    demo = build_ui(args.proxy_url, args.api_key)
    demo.launch(server_name=args.host, server_port=args.port, show_error=True)


if __name__ == "__main__":
    main()
