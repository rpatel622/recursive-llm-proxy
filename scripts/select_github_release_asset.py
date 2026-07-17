#!/usr/bin/env python3
"""Download one GitHub release asset selected by ordered filename patterns.

Each pattern may contain ``+``-separated required substrings. For example,
``cpython-3.11+x86_64-pc-windows-msvc+install_only`` matches an asset whose
filename contains all three fragments, regardless of order or case.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path


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


def _matches(name: str, expression: str) -> bool:
    lowered = name.lower()
    required = [part.strip().lower() for part in expression.split("+") if part.strip()]
    return bool(required) and all(part in lowered for part in required)


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

    selected = None
    for pattern in args.patterns:
        matches = [asset for asset in assets if _matches(asset.get("name", ""), pattern)]
        if len(matches) == 1:
            selected = matches[0]
            break
        if len(matches) > 1:
            names = ", ".join(asset["name"] for asset in matches)
            raise SystemExit(f"Pattern {pattern!r} matched multiple assets: {names}")

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
