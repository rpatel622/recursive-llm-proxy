"""Secured administrative control plane for local RLM operations."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import Response

from .admin_security import ApiKeyRegistry, ApiPrincipal, TokenBucketLimiter
from .audit_log import AuditLog
from .catalog_transfer import backup_catalog_database, export_catalog, import_catalog
from .routing import registry
from .stack_health import HealthCheck, check_stack


def _load_principals() -> ApiKeyRegistry:
    secret = os.getenv("RLM_PROXY_ADMIN_REGISTRY_SECRET", "local-development-secret").encode()
    principals = ApiKeyRegistry(secret)
    raw = os.getenv("RLM_PROXY_ADMIN_KEYS_JSON", "{}")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("RLM_PROXY_ADMIN_KEYS_JSON must be an object")
    for api_key, config in value.items():
        if not isinstance(config, dict):
            raise ValueError("admin key configuration must be an object")
        principals.register(
            str(api_key),
            str(config.get("principal_id") or "admin"),
            [str(scope) for scope in config.get("scopes", ["admin:*"])],
        )
    return principals


def _bearer(authorization: Optional[str]) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail={"message": "missing bearer token"})
    return authorization[7:]


def create_control_plane(
    checks: Iterable[HealthCheck] = (),
    key_registry: Optional[ApiKeyRegistry] = None,
    limiter: Optional[TokenBucketLimiter] = None,
    audit_log: Optional[AuditLog] = None,
) -> FastAPI:
    app = FastAPI(title="recursive-llm control plane", version="1.0.0")
    keys = key_registry or _load_principals()
    rate_limiter = limiter or TokenBucketLimiter(
        capacity=int(os.getenv("RLM_PROXY_ADMIN_RATE_CAPACITY", "60")),
        refill_per_second=float(os.getenv("RLM_PROXY_ADMIN_RATE_REFILL", "1")),
    )
    audit = audit_log or AuditLog(
        Path(os.getenv("RLM_PROXY_AUDIT_LOG", "~/.recursive-llm/audit.jsonl"))
    )
    health_checks = list(checks)

    def principal(
        authorization: Optional[str] = Header(default=None),
    ) -> ApiPrincipal:
        resolved = keys.authenticate(_bearer(authorization))
        if resolved is None:
            raise HTTPException(status_code=401, detail={"message": "invalid API key"})
        if not rate_limiter.allow(resolved.principal_id):
            raise HTTPException(status_code=429, detail={"message": "rate limit exceeded"})
        return resolved

    def require(scope: str):
        def dependency(actor: ApiPrincipal = Depends(principal)) -> ApiPrincipal:
            try:
                actor.require(scope)
            except PermissionError as exc:
                raise HTTPException(status_code=403, detail={"message": str(exc)}) from exc
            return actor

        return dependency

    @app.get("/healthz")
    async def healthz() -> Dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz() -> Dict[str, Any]:
        return check_stack(health_checks)

    @app.get("/v1/admin/catalog/export")
    async def catalog_export(
        actor: ApiPrincipal = Depends(require("catalog:read")),
    ) -> Response:
        payload = export_catalog(registry)
        audit.append(actor.principal_id, "catalog.export", "catalog", "success")
        return Response(
            content=payload,
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="rlm-catalog.json"'},
        )

    @app.post("/v1/admin/catalog/import")
    async def catalog_import(
        request: Request,
        expected_version: Optional[int] = None,
        actor: ApiPrincipal = Depends(require("catalog:write")),
    ) -> Dict[str, Any]:
        try:
            snapshot = import_catalog(
                registry,
                await request.body(),
                expected_version=expected_version,
            )
        except ValueError as exc:
            audit.append(
                actor.principal_id,
                "catalog.import",
                "catalog",
                "failure",
                {"error": str(exc)},
            )
            status = 409 if "version conflict" in str(exc) else 400
            raise HTTPException(status_code=status, detail={"message": str(exc)}) from exc
        audit.append(
            actor.principal_id,
            "catalog.import",
            "catalog",
            "success",
            {"version": snapshot.version},
        )
        return snapshot.model_dump()

    @app.post("/v1/admin/catalog/backup")
    async def catalog_backup(
        destination: str,
        actor: ApiPrincipal = Depends(require("catalog:backup")),
    ) -> Dict[str, Any]:
        path = backup_catalog_database(registry, Path(destination))
        audit.append(
            actor.principal_id,
            "catalog.backup",
            str(path),
            "success",
        )
        return {"path": str(path)}

    @app.get("/v1/admin/audit")
    async def audit_events(
        limit: int = 100,
        actor: ApiPrincipal = Depends(require("audit:read")),
    ) -> Dict[str, Any]:
        events = audit.read()[-max(0, limit) :]
        audit.append(actor.principal_id, "audit.read", "audit", "success", {"limit": limit})
        return {"verified": audit.verify(), "data": [event.__dict__ for event in events]}

    @app.get("/v1/admin/audit/verify")
    async def verify_audit(
        actor: ApiPrincipal = Depends(require("audit:read")),
    ) -> Dict[str, Any]:
        verified = audit.verify()
        audit.append(actor.principal_id, "audit.verify", "audit", "success")
        return {"verified": verified}

    return app


app = create_control_plane()

__all__ = ["app", "create_control_plane"]
