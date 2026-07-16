"""End-to-end example for the recursive-llm proxy fork."""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
from openai import OpenAI


BASE_URL = os.environ.get("RLM_PROXY_BASE_URL", "http://127.0.0.1:8000")
API_KEY = os.environ.get("RLM_PROXY_API_KEY", "local-public-key")
EXAMPLES_DIR = Path(__file__).resolve().parent


def load_json(name: str) -> dict:
    with (EXAMPLES_DIR / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def register_slots() -> None:
    response = httpx.put(
        f"{BASE_URL}/v1/rlm/slots",
        headers={"Authorization": f"Bearer {API_KEY}"},
        json=load_json("slot_setup.json"),
        timeout=30.0,
    )
    response.raise_for_status()


def main() -> None:
    register_slots()

    client = OpenAI(base_url=f"{BASE_URL}/v1", api_key=API_KEY)
    response = client.chat.completions.create(
        model="rlm",
        messages=[
            {
                "role": "user",
                "content": "What is the production rollback trigger?",
            }
        ],
        extra_body={
            "rlm": {
                "routing": {
                    "mode": "auto",
                    "initial_turn_count": 2,
                    "max_turn_count": 32,
                    "allow_multi_workstream": True,
                    "allow_cross_slot": False,
                },
                "max_depth": 2,
                "max_total_calls": 24,
                "max_elapsed_seconds": 300,
            }
        },
    )

    print(response.choices[0].message.content)
    routing = getattr(response, "rlm", None)
    if routing is not None:
        print(routing)


if __name__ == "__main__":
    main()
