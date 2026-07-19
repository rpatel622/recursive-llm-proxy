"""Measure knowledge ingestion, retrieval, reranking, storage, and process baselines."""

from __future__ import annotations

import argparse
import base64
import json
import os
import resource
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import httpx

BASELINE_VERSION = 1


@dataclass(frozen=True)
class TimingSummary:
    count: int
    minimum_ms: float
    median_ms: float
    p95_ms: float
    maximum_ms: float
    mean_ms: float


@dataclass(frozen=True)
class ProfileReport:
    baseline_version: int
    corpus_documents: int
    corpus_bytes: int
    database_bytes: Optional[int]
    process_peak_rss_kib: int
    ingestion: TimingSummary
    search_without_rerank: TimingSummary
    search_with_rerank: TimingSummary
    generated_at_unix: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def summarize(samples_ms: Iterable[float]) -> TimingSummary:
    values = sorted(float(value) for value in samples_ms)
    if not values:
        return TimingSummary(0, 0.0, 0.0, 0.0, 0.0, 0.0)
    p95_index = min(len(values) - 1, max(0, int(round(0.95 * len(values) + 0.5)) - 1))
    return TimingSummary(
        count=len(values),
        minimum_ms=values[0],
        median_ms=statistics.median(values),
        p95_ms=values[p95_index],
        maximum_ms=values[-1],
        mean_ms=statistics.fmean(values),
    )


def _timed_request(client: httpx.Client, method: str, url: str, **kwargs: Any) -> tuple[float, Any]:
    started = time.perf_counter()
    response = client.request(method, url, **kwargs)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    response.raise_for_status()
    return elapsed_ms, response.json()


def profile(
    api_base: str,
    corpus_dir: Path,
    queries: List[str],
    database_path: Optional[Path] = None,
    repetitions: int = 3,
    timeout_seconds: float = 120.0,
) -> ProfileReport:
    files = sorted(path for path in corpus_dir.rglob("*") if path.is_file())
    if not files:
        raise ValueError("corpus directory contains no files")
    if not queries:
        raise ValueError("at least one query is required")
    if repetitions <= 0:
        raise ValueError("repetitions must be greater than zero")

    ingestion_samples: List[float] = []
    no_rerank_samples: List[float] = []
    rerank_samples: List[float] = []
    corpus_bytes = sum(path.stat().st_size for path in files)
    base = api_base.rstrip("/")

    with httpx.Client(timeout=timeout_seconds) as client:
        for path in files:
            payload = {
                "source_uri": path.resolve().as_uri(),
                "media_type": _media_type(path),
                "content_base64": base64.b64encode(path.read_bytes()).decode("ascii"),
            }
            elapsed, _ = _timed_request(
                client,
                "POST",
                f"{base}/v1/knowledge/ingest",
                json=payload,
            )
            ingestion_samples.append(elapsed)

        for _ in range(repetitions):
            for query in queries:
                common = {
                    "query": query,
                    "candidate_limit": 24,
                    "limit": 6,
                    "max_context_chars": 24000,
                }
                elapsed, _ = _timed_request(
                    client,
                    "POST",
                    f"{base}/v1/knowledge/search",
                    json={**common, "rerank": False},
                )
                no_rerank_samples.append(elapsed)
                elapsed, _ = _timed_request(
                    client,
                    "POST",
                    f"{base}/v1/knowledge/search",
                    json={**common, "rerank": True},
                )
                rerank_samples.append(elapsed)

    database_bytes = None
    if database_path is not None and database_path.exists():
        database_bytes = database_path.stat().st_size
    return ProfileReport(
        baseline_version=BASELINE_VERSION,
        corpus_documents=len(files),
        corpus_bytes=corpus_bytes,
        database_bytes=database_bytes,
        process_peak_rss_kib=int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
        ingestion=summarize(ingestion_samples),
        search_without_rerank=summarize(no_rerank_samples),
        search_with_rerank=summarize(rerank_samples),
        generated_at_unix=int(time.time()),
    )


def _media_type(path: Path) -> str:
    return {
        ".txt": "text/plain",
        ".md": "text/markdown",
        ".html": "text/html",
        ".htm": "text/html",
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }.get(path.suffix.lower(), "application/octet-stream")


def main() -> int:
    parser = argparse.ArgumentParser(description="Profile the native knowledge service")
    parser.add_argument("--api-base", default=os.getenv("RLM_KNOWLEDGE_API_BASE", "http://127.0.0.1:8010"))
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--query", action="append", dest="queries", required=True)
    parser.add_argument("--database", type=Path)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = profile(
        api_base=args.api_base,
        corpus_dir=args.corpus,
        queries=args.queries,
        database_path=args.database,
        repetitions=args.repetitions,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
