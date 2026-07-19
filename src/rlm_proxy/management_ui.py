"""Standalone Gradio management UI for catalogs and knowledge operations."""

from __future__ import annotations

import argparse
import json
import mimetypes
from pathlib import Path
from typing import Any, Dict, Tuple

from .catalog_editor import CatalogEditorController
from .knowledge_browser import KnowledgeBrowserController
from .ui_clients import ApiClientConfig, CatalogApiClient, KnowledgeApiClient


def _controllers(proxy_url: str, knowledge_url: str, api_key: str) -> Tuple[CatalogEditorController, KnowledgeBrowserController]:
    catalog = CatalogEditorController(CatalogApiClient(ApiClientConfig(proxy_url, api_key)))
    knowledge = KnowledgeBrowserController(KnowledgeApiClient(ApiClientConfig(knowledge_url)))
    return catalog, knowledge


def refresh_catalog(proxy_url: str, api_key: str) -> Tuple[str, int]:
    catalog, _ = _controllers(proxy_url, "http://127.0.0.1:8010", api_key)
    snapshot = catalog.refresh()
    return json.dumps(snapshot.slots, indent=2, ensure_ascii=False), snapshot.version


def replace_catalog(proxy_url: str, api_key: str, slots_json: str, version: float) -> Tuple[str, int, str]:
    try:
        value = json.loads(slots_json)
        if not isinstance(value, list):
            raise ValueError("slots JSON must be a list")
        catalog, _ = _controllers(proxy_url, "http://127.0.0.1:8010", api_key)
        snapshot = catalog.replace(value, int(version))
        return json.dumps(snapshot.slots, indent=2, ensure_ascii=False), snapshot.version, "Catalog saved"
    except Exception as exc:
        return slots_json, int(version), f"Save failed: {exc}"


def append_turn(
    proxy_url: str,
    api_key: str,
    slots_json: str,
    version: float,
    slot_slug: str,
    workstream_slug: str,
    role: str,
    content: str,
) -> Tuple[str, int, str]:
    try:
        catalog, _ = _controllers(proxy_url, "http://127.0.0.1:8010", api_key)
        snapshot = catalog.append_turn(slot_slug, workstream_slug, role, content, int(version))
        return json.dumps(snapshot.slots, indent=2, ensure_ascii=False), snapshot.version, "Turn appended"
    except Exception as exc:
        return slots_json, int(version), f"Append failed: {exc}"


def refresh_knowledge(knowledge_url: str) -> Tuple[Dict[str, Any], Dict[str, Any], Any, Any]:
    _, knowledge = _controllers("http://127.0.0.1:8000", knowledge_url, "")
    snapshot = knowledge.refresh()
    return snapshot.health, snapshot.stats, snapshot.documents, snapshot.jobs


def search_knowledge(knowledge_url: str, query: str, limit: float) -> Dict[str, Any]:
    _, knowledge = _controllers("http://127.0.0.1:8000", knowledge_url, "")
    return knowledge.search(query, int(limit))


def upload_knowledge(knowledge_url: str, file_path: str) -> Tuple[str, Dict[str, Any]]:
    try:
        path = Path(file_path)
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        _, knowledge = _controllers("http://127.0.0.1:8000", knowledge_url, "")
        result = knowledge.upload(path, media_type)
        return "Upload queued", result
    except Exception as exc:
        return f"Upload failed: {exc}", {}


def build_management_ui(
    proxy_url: str = "http://127.0.0.1:8000",
    knowledge_url: str = "http://127.0.0.1:8010",
    api_key: str = "",
) -> Any:
    import gradio as gr

    with gr.Blocks(title="Local RLM Management") as demo:
        gr.Markdown("# Local RLM Management")
        with gr.Row():
            proxy = gr.Textbox(label="Proxy URL", value=proxy_url)
            knowledge = gr.Textbox(label="Knowledge URL", value=knowledge_url)
            key = gr.Textbox(label="Proxy API key", value=api_key, type="password")

        with gr.Tab("Knowledge"):
            refresh = gr.Button("Refresh", variant="primary")
            with gr.Row():
                health = gr.JSON(label="Health")
                stats = gr.JSON(label="Statistics")
            documents = gr.JSON(label="Documents")
            jobs = gr.JSON(label="Jobs")
            refresh.click(refresh_knowledge, inputs=[knowledge], outputs=[health, stats, documents, jobs])

            with gr.Row():
                query = gr.Textbox(label="Search query")
                limit = gr.Number(label="Results", value=6, precision=0)
                search_button = gr.Button("Search")
            search_results = gr.JSON(label="Search results")
            search_button.click(search_knowledge, inputs=[knowledge, query, limit], outputs=search_results)

            file_input = gr.File(label="Upload document", type="filepath")
            upload_button = gr.Button("Queue ingestion")
            upload_status = gr.Textbox(label="Upload status", interactive=False)
            upload_result = gr.JSON(label="Job")
            upload_button.click(upload_knowledge, inputs=[knowledge, file_input], outputs=[upload_status, upload_result])

        with gr.Tab("Catalog"):
            catalog_status = gr.Textbox(label="Status", interactive=False)
            version = gr.Number(label="Catalog version", value=0, precision=0)
            slots = gr.Code(label="Slots JSON", language="json", lines=24)
            with gr.Row():
                load = gr.Button("Load")
                save = gr.Button("Save", variant="primary")
            load.click(refresh_catalog, inputs=[proxy, key], outputs=[slots, version])
            save.click(replace_catalog, inputs=[proxy, key, slots, version], outputs=[slots, version, catalog_status])

            with gr.Row():
                slot_slug = gr.Textbox(label="Slot slug")
                workstream_slug = gr.Textbox(label="Workstream slug")
                role = gr.Dropdown(["user", "assistant", "system"], value="user", label="Role")
            content = gr.Textbox(label="Turn content", lines=4)
            append = gr.Button("Append turn")
            append.click(
                append_turn,
                inputs=[proxy, key, slots, version, slot_slug, workstream_slug, role, content],
                outputs=[slots, version, catalog_status],
            )

    return demo


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Local RLM management UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7861)
    parser.add_argument("--proxy-url", default="http://127.0.0.1:8000")
    parser.add_argument("--knowledge-url", default="http://127.0.0.1:8010")
    parser.add_argument("--api-key", default="")
    args = parser.parse_args()
    build_management_ui(args.proxy_url, args.knowledge_url, args.api_key).launch(
        server_name=args.host,
        server_port=args.port,
        show_error=True,
    )


if __name__ == "__main__":
    main()
