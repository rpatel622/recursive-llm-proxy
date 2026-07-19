"""Typed HTTP client boundary used by browser and admin interfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx


class ApiClientError(RuntimeError):
    """Base error for management API clients."""


class VersionConflictError(ApiClientError):
    """The caller attempted a mutation against a stale catalog version."""


class ServiceUnavailableError(ApiClientError):
    """The target local service could not be reached."""


@dataclass(frozen=True)
class ApiClientConfig:
    api_base: str
    api_key: str = ""
    timeout_seconds: float = 15.0

    def headers(self) -> Dict[str, str]:
        if not self.api_key:
            return {}
        return {"Authorization": f"Bearer {self.api_key}"}


class _BaseClient:
    def __init__(self, config: ApiClientConfig, client: Optional[httpx.Client] = None) -> None:
        self.config = config
        self._client = client or httpx.Client(timeout=config.timeout_seconds)

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        headers = dict(self.config.headers())
        headers.update(kwargs.pop("headers", {}))
        try:
            response = self._client.request(
                method,
                f"{self.config.api_base.rstrip('/')}{path}",
                headers=headers,
                **kwargs,
            )
        except httpx.HTTPError as exc:
            raise ServiceUnavailableError(str(exc)) from exc
        if response.status_code == 409:
            message = _error_message(response)
            raise VersionConflictError(message)
        if response.status_code >= 500:
            raise ServiceUnavailableError(_error_message(response))
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ApiClientError(_error_message(response)) from exc
        return response


class CatalogApiClient(_BaseClient):
    def get_catalog(self) -> Dict[str, Any]:
        return dict(self._request("GET", "/v1/rlm/slots").json())

    def replace_catalog(self, catalog: Dict[str, Any]) -> Dict[str, Any]:
        return dict(self._request("PUT", "/v1/rlm/slots", json=catalog).json())

    def append_turn(
        self,
        slot_slug: str,
        workstream_slug: str,
        role: str,
        content: str,
        expected_version: Optional[int] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"role": role, "content": content}
        if expected_version is not None:
            payload["expected_version"] = expected_version
        return dict(
            self._request(
                "POST",
                f"/v1/rlm/slots/{slot_slug}/workstreams/{workstream_slug}/turns",
                json=payload,
            ).json()
        )

    def delete_workstream(
        self,
        slot_slug: str,
        workstream_slug: str,
        expected_version: Optional[int] = None,
    ) -> Dict[str, Any]:
        headers = {}
        if expected_version is not None:
            headers["If-Match"] = f'"{expected_version}"'
        return dict(
            self._request(
                "DELETE",
                f"/v1/rlm/slots/{slot_slug}/workstreams/{workstream_slug}",
                headers=headers,
            ).json()
        )


class KnowledgeApiClient(_BaseClient):
    def health(self) -> Dict[str, Any]:
        return dict(self._request("GET", "/healthz").json())

    def list_documents(self) -> List[Dict[str, Any]]:
        value = self._request("GET", "/v1/knowledge/documents").json()
        return [dict(item) for item in value]

    def stats(self) -> Dict[str, Any]:
        return dict(self._request("GET", "/v1/knowledge/stats").json())

    def search(
        self,
        query: str,
        candidate_limit: int = 24,
        limit: int = 6,
        rerank: bool = True,
        max_context_chars: int = 24000,
    ) -> Dict[str, Any]:
        return dict(
            self._request(
                "POST",
                "/v1/knowledge/search",
                json={
                    "query": query,
                    "candidate_limit": candidate_limit,
                    "limit": limit,
                    "rerank": rerank,
                    "max_context_chars": max_context_chars,
                },
            ).json()
        )

    def enqueue_ingestion(
        self,
        source_uri: str,
        media_type: str,
        content_base64: str,
    ) -> Dict[str, Any]:
        return dict(
            self._request(
                "POST",
                "/v1/knowledge/jobs",
                json={
                    "source_uri": source_uri,
                    "media_type": media_type,
                    "content_base64": content_base64,
                },
            ).json()
        )

    def list_jobs(self) -> List[Dict[str, Any]]:
        value = self._request("GET", "/v1/knowledge/jobs").json()
        return [dict(item) for item in value]

    def get_job(self, job_id: str) -> Dict[str, Any]:
        return dict(self._request("GET", f"/v1/knowledge/jobs/{job_id}").json())

    def cancel_job(self, job_id: str) -> Dict[str, Any]:
        return dict(self._request("DELETE", f"/v1/knowledge/jobs/{job_id}").json())

    def delete_document(self, document_id: str) -> Dict[str, Any]:
        return dict(self._request("DELETE", f"/v1/knowledge/documents/{document_id}").json())


def _error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text or f"HTTP {response.status_code}"
    if isinstance(payload, dict):
        detail = payload.get("detail") or payload.get("error")
        if isinstance(detail, dict) and detail.get("message"):
            return str(detail["message"])
        if isinstance(detail, str):
            return detail
    return f"HTTP {response.status_code}"
