from __future__ import annotations

import importlib.util
from pathlib import Path


def load_module():
    script = Path(__file__).parents[1] / "scripts" / "optimize_bundle.py"
    spec = importlib.util.spec_from_file_location("optimize_bundle", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_optimize_removes_only_known_build_waste(tmp_path: Path) -> None:
    module = load_module()
    root = tmp_path / "bundle"
    package = root / "runtime/python/Lib/site-packages/example"
    cache = package / "__pycache__"
    stdlib_test = root / "runtime/python/Lib/test"
    package.mkdir(parents=True)
    cache.mkdir()
    stdlib_test.mkdir(parents=True)

    source = package / "__init__.py"
    bytecode = cache / "__init__.cpython-311.pyc"
    test_file = stdlib_test / "test_runtime.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    bytecode.write_bytes(b"bytecode")
    test_file.write_text("assert True\n", encoding="utf-8")

    removed = module.optimize(root)

    assert source.exists()
    assert not cache.exists()
    assert not stdlib_test.exists()
    assert removed["cache_and_bytecode"] == len(b"bytecode")
    assert removed["stdlib_development_files"] == len("assert True\n")


def test_report_attributes_dependency_and_file_sizes(tmp_path: Path) -> None:
    module = load_module()
    root = tmp_path / "bundle"
    dependency = root / "runtime/python/Lib/site-packages/large_package"
    dependency.mkdir(parents=True)
    payload_file = dependency / "payload.bin"
    payload_file.write_bytes(b"x" * 128)

    payload = module.report(
        root,
        {"cache_and_bytecode": 0, "stdlib_development_files": 0},
        limit=10,
    )

    assert payload["total_bytes"] == 128
    assert payload["largest_dependencies"][0] == {
        "path": "runtime/python/Lib/site-packages/large_package",
        "bytes": 128,
    }
    assert payload["largest_files"][0] == {
        "path": "runtime/python/Lib/site-packages/large_package/payload.bin",
        "bytes": 128,
    }
