#!/usr/bin/env python3
"""Download one GitHub release asset selected by ordered filename patterns.

Each pattern may contain ``+``-separated required substrings. For example,
``cpython-3.11+x86_64-pc-windows-msvc+install_only`` matches an asset whose
filename contains all fragments, regardless of order or case.

When multiple assets match, the resolver ranks them deterministically. Exact
requested variants are preferred, while unrequested variants such as
``install_only_stripped`` are treated as fallbacks rather than causing the
workflow to fail.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


def _request(url: str) -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "recursive-llm-bundler",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as response:
        return json.load(response)


def _download(url: str, destination: Path) -> None:
    headers = {"User-Agent": "recursive-llm-bundler"}
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=300) as response:
        with destination.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)


def _parts(expression: str) -> List[str]:
    return [part.strip().lower() for part in expression.split("+") if part.strip()]


def _matches(name: str, expression: str) -> bool:
    lowered = name.lower()
    required = _parts(expression)
    return bool(required) and all(part in lowered for part in required)


def _variant_penalty(name: str, required: Sequence[str]) -> int:
    """Penalize common variants unless the expression explicitly requests them."""

    lowered = name.lower()
    requested = " ".join(required)
    penalty = 0
    for marker in ("stripped", "debug", "pdb", "freethreaded"):
        if marker in lowered and marker not in requested:
            penalty += 100
    return penalty


def _rank(name: str, expression: str) -> Tuple[int, int, str]:
    """Return a stable rank where lower values are preferred."""

    required = _parts(expression)
    lowered = name.lower()
    unmatched_length = len(lowered) - sum(len(part) for part in required)
    return (_variant_penalty(lowered, required), unmatched_length, lowered)


def _select_asset(assets: Iterable[Dict[str, Any]], patterns: Sequence[str]) -> Optional[Dict[str, Any]]:
    """Select the best asset using pattern order followed by deterministic ranking."""

    asset_list = list(assets)
    for pattern in patterns:
        matches = [asset for asset in asset_list if _matches(str(asset.get("name", "")), pattern)]
        if matches:
            return min(matches, key=lambda asset: _rank(str(asset.get("name", "")), pattern))
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repository", help="GitHub repository in owner/name form")
    parser.add_argument("destination", type=Path)
    parser.add_argument("patterns", nargs="+", help="Ordered filename expressions")
    parser.add_argument("--tag", help="Specific release tag; defaults to latest")
    args = parser.parse_args()

    endpoint = (
        f"https://api.github.com/repos/{args.repository}/releases/tags/{args.tag}"
        if args.tag
        else f"https://api.github.com/repos/{args.repository}/releases/latest"
    )
    release = _request(endpoint)
    assets = release.get("assets", [])
    selected = _select_asset(assets, args.patterns)

    if selected is None:
        available = "\n".join(f"- {asset.get('name')}" for asset in assets)
        raise SystemExit(
            "No release asset matched any requested pattern.\n"
            f"Repository: {args.repository}\nPatterns: {args.patterns}\nAvailable:\n{available}"
        )

    print(f"Downloading {selected['name']} from release {release.get('tag_name')}")
    _download(selected["browser_download_url"], args.destination)
    args.destination.with_suffix(args.destination.suffix + ".json").write_text(
        json.dumps(
            {
                "repository": args.repository,
                "release": release.get("tag_name"),
                "asset": selected["name"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
