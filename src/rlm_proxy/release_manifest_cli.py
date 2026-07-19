"""Command-line interface for release manifest generation and verification."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable, Optional

from .release_manifest import build_manifest, encode_manifest, verify_manifest


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Generate or verify a release manifest")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate")
    generate.add_argument("root", type=Path)
    generate.add_argument("output", type=Path)
    generate.add_argument("paths", nargs="+")

    verify = subparsers.add_parser("verify")
    verify.add_argument("root", type=Path)
    verify.add_argument("manifest", type=Path)

    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.command == "generate":
        manifest = build_manifest(args.root, args.paths)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(encode_manifest(manifest))
        return 0

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    failures = verify_manifest(args.root, manifest)
    for failure in failures:
        print(failure)
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
