from pathlib import Path

import pytest

from rlm_proxy.release_manifest import build_manifest, encode_manifest, verify_manifest


def test_manifest_is_deterministic_and_verifies(tmp_path: Path) -> None:
    (tmp_path / "b.txt").write_text("beta", encoding="utf-8")
    (tmp_path / "a.txt").write_text("alpha", encoding="utf-8")

    manifest = build_manifest(tmp_path, ["b.txt", "a.txt", "a.txt"])

    assert [item["path"] for item in manifest["files"]] == ["a.txt", "b.txt"]
    assert encode_manifest(manifest).endswith(b"\n")
    assert verify_manifest(tmp_path, manifest) == []


def test_manifest_reports_modified_and_missing_files(tmp_path: Path) -> None:
    path = tmp_path / "file.txt"
    path.write_text("original", encoding="utf-8")
    manifest = build_manifest(tmp_path, ["file.txt"])
    path.write_text("changed", encoding="utf-8")

    assert verify_manifest(tmp_path, manifest) == ["size mismatch: file.txt"]
    path.unlink()
    assert verify_manifest(tmp_path, manifest) == ["missing: file.txt"]


def test_manifest_rejects_unknown_version(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unsupported"):
        verify_manifest(tmp_path, {"manifest_version": 99, "files": []})
