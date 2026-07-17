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


def test_prefers_plain_install_only_over_unrequested_stripped_variant() -> None:
    assets = [
        {
            "name": "cpython-3.11.15+20260623-x86_64-pc-windows-msvc-install_only_stripped.tar.gz",
            "browser_download_url": "https://example.test/stripped",
        },
        {
            "name": "cpython-3.11.15+20260623-x86_64-pc-windows-msvc-install_only.tar.gz",
            "browser_download_url": "https://example.test/plain",
        },
    ]

    selected = MODULE._select_asset(
        assets,
        ["cpython-3.11+x86_64-pc-windows-msvc+install_only"],
    )

    assert selected is not None
    assert selected["browser_download_url"] == "https://example.test/plain"


def test_can_explicitly_request_stripped_variant() -> None:
    assets = [
        {"name": "runtime-install_only.tar.gz"},
        {"name": "runtime-install_only_stripped.tar.gz"},
    ]

    selected = MODULE._select_asset(assets, ["runtime+install_only+stripped"])

    assert selected is not None
    assert selected["name"] == "runtime-install_only_stripped.tar.gz"


def test_uses_next_pattern_when_preferred_variant_is_unavailable() -> None:
    assets = [{"name": "llama-bin-win-cpu-x64.zip"}]

    selected = MODULE._select_asset(
        assets,
        ["llama+win+vulkan+x64", "llama+win+cpu+x64"],
    )

    assert selected is not None
    assert selected["name"] == "llama-bin-win-cpu-x64.zip"
