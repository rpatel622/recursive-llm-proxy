from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "select_github_release_asset.py"
SPEC = importlib.util.spec_from_file_location("release_asset_selector", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_matches_all_conjunctive_fragments_case_insensitively() -> None:
    name = "cpython-3.11.11+20250101-X86_64-PC-WINDOWS-MSVC-install_only.tar.gz"
    assert MODULE._matches(name, "cpython-3.11+x86_64-pc-windows-msvc+install_only")


def test_rejects_when_one_required_fragment_is_missing() -> None:
    name = "cpython-3.11.11-x86_64-unknown-linux-gnu-install_only.tar.gz"
    assert not MODULE._matches(name, "cpython-3.11+aarch64-unknown-linux-gnu+install_only")


def test_empty_expression_does_not_match() -> None:
    assert not MODULE._matches("anything.zip", "++")
