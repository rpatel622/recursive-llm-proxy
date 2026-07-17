#!/usr/bin/env python3
"""Remove safe build-time waste and report bundle size contributors."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

CACHE_DIR_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
BYTECODE_SUFFIXES = {".pyc", ".pyo"}
STDLIB_PRUNE_RELATIVE = (
    Path("Lib/test"),
    Path("Lib/idlelib"),
    Path("Lib/turtledemo"),
    Path("Lib/tkinter/test"),
    Path("lib/python3.11/test"),
    Path("lib/python3.11/idlelib"),
    Path("lib/python3.11/turtledemo"),
    Path("lib/python3.11/tkinter/test"),
)


def file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def tree_size(path: Path) -> int:
    if path.is_file():
        return file_size(path)
    return sum(file_size(candidate) for candidate in path.rglob("*") if candidate.is_file())


def human_size(value: int) -> str:
    amount = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if amount < 1024 or unit == "TiB":
            return f"{amount:.1f} {unit}"
        amount /= 1024
    raise AssertionError("unreachable")


def remove_path(path: Path) -> int:
    removed = tree_size(path)
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)
    return removed


def optimize(root: Path) -> dict[str, int]:
    removed = {"cache_and_bytecode": 0, "stdlib_development_files": 0}

    candidates = sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True)
    for path in candidates:
        if not path.exists():
            continue
        if path.is_dir() and path.name in CACHE_DIR_NAMES:
            removed["cache_and_bytecode"] += remove_path(path)
        elif path.is_file() and path.suffix.lower() in BYTECODE_SUFFIXES:
            removed["cache_and_bytecode"] += remove_path(path)

    python_root = root / "runtime" / "python"
    for relative in STDLIB_PRUNE_RELATIVE:
        path = python_root / relative
        if path.exists():
            removed["stdlib_development_files"] += remove_path(path)

    return removed


def report(root: Path, removed: dict[str, int], limit: int) -> dict[str, object]:
    top_level = sorted(
        ((tree_size(path), path.relative_to(root).as_posix()) for path in root.iterdir()),
        reverse=True,
    )
    files = sorted(
        ((file_size(path), path.relative_to(root).as_posix()) for path in root.rglob("*") if path.is_file()),
        reverse=True,
    )

    dependency_roots = [
        root / "runtime" / "python" / "Lib" / "site-packages",
        root / "runtime" / "python" / "lib" / "python3.11" / "site-packages",
    ]
    dependency_entries: list[tuple[int, str]] = []
    for dependency_root in dependency_roots:
        if dependency_root.exists():
            dependency_entries.extend(
                (tree_size(path), path.relative_to(root).as_posix())
                for path in dependency_root.iterdir()
            )
    dependency_entries.sort(reverse=True)

    return {
        "schema": 1,
        "total_bytes": tree_size(root),
        "removed_bytes": removed,
        "top_level": [
            {"path": path, "bytes": size} for size, path in top_level[:limit]
        ],
        "largest_dependencies": [
            {"path": path, "bytes": size} for size, path in dependency_entries[:limit]
        ],
        "largest_files": [
            {"path": path, "bytes": size} for size, path in files[:limit]
        ],
    }


def print_report(payload: dict[str, object]) -> None:
    print(f"Optimized bundle total: {human_size(int(payload['total_bytes']))}")
    removed = payload["removed_bytes"]
    assert isinstance(removed, dict)
    for category, value in removed.items():
        print(f"Removed {category}: {human_size(int(value))}")

    for heading, key in (
        ("Top-level components", "top_level"),
        ("Largest installed dependencies", "largest_dependencies"),
        ("Largest files", "largest_files"),
    ):
        print(f"\n{heading}:")
        entries = payload[key]
        assert isinstance(entries, list)
        for entry in entries:
            assert isinstance(entry, dict)
            print(f"{human_size(int(entry['bytes'])):>12}  {entry['path']}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--limit", type=int, default=40)
    args = parser.parse_args()

    root = args.root.resolve()
    if not root.is_dir():
        parser.error(f"bundle root does not exist: {root}")

    removed = optimize(root)
    payload = report(root, removed, max(args.limit, 1))
    print_report(payload)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
