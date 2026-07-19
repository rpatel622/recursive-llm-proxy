"""Authenticated HTTP service for catalog export, import, and backup operations."""

from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field

from .catalog_transfer import backup_catalog_database, export_catalog, import_catalog
from .routing import registry


class ImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payload: str = Field(min_length=1)
    expected_version: Optional[int] = Field(default=None, ge=0)


class BackupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    destination: str = Field(min_length=1)


def _verify(authorization: Optional[str] = Header(default=None)) -> None:
    api_key = os.getenv("RLM_PROXY_PUBLIC_API_KEY", "").strip()
    if not api_key:
        return
    expected = f"Bearer {api_key}"
    if authorization is None or not secrets.compare_digest(authorization, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


def create_catalog_transfer_app() -> FastAPI:
    app = FastAPI(title="RLM catalog transfer service", version="1.0")

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/rlm/catalog/export")
    async def export(authorization: Optional[str] = Header(default=None)) -> Response:
        _verify(authorization)
        return Response(
            content=export_catalog(registry),
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="rlm-catalog.json"'},
        )

    @app.post("/v1/rlm/catalog/import")
    async def import_value(
        request: ImportRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> dict[str, object]:
        _verify(authorization)
        try:
            stored = import_catalog(
                registry,
                request.payload.encode("utf-8"),
                expected_version=request.expected_version,
            )
        except ValueError as exc:
            code = 409 if "version conflict" in str(exc) else 400
            raise HTTPException(status_code=code, detail={"message": str(exc)}) from exc
        return stored.model_dump()

    @app.post("/v1/rlm/catalog/backup")
    async def backup(
        request: BackupRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> dict[str, str]:
        _verify(authorization)
        try:
            destination = backup_catalog_database(registry, Path(request.destination))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"message": str(exc)}) from exc
        return {"path": str(destination)}

    return app


app = create_catalog_transfer_app()
