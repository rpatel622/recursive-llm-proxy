"""HTTP routes for append-oriented catalog mutations."""

from __future__ import annotations

from typing import Any, Callable, Dict, Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field

from .models import StoredTurn
from .routing import normalized_catalog, registry


class AppendTurnRequest(BaseModel):
    """Append one immutable turn to an existing workstream."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "developer", "user", "assistant", "tool"]
    content: str = Field(min_length=1)
    expected_version: Optional[int] = Field(default=None, ge=0)


class DeleteWorkstreamRequest(BaseModel):
    """Optional optimistic-concurrency input for workstream deletion."""

    model_config = ConfigDict(extra="forbid")

    expected_version: Optional[int] = Field(default=None, ge=0)


def _expected_version(body_version: Optional[int], if_match: Optional[str]) -> Optional[int]:
    if body_version is not None:
        return body_version
    if if_match is None:
        return None
    value = if_match.strip().strip('"')
    try:
        return int(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"message": "If-Match must be an integer"},
        ) from exc


def _mutation_error(exc: ValueError) -> HTTPException:
    message = str(exc)
    code = (
        status.HTTP_409_CONFLICT
        if "version conflict" in message
        else status.HTTP_404_NOT_FOUND
    )
    return HTTPException(status_code=code, detail={"message": message})


def build_catalog_mutation_router(auth_dependency: Callable[..., Any]) -> APIRouter:
    """Build routes without importing the application module and creating a cycle."""

    router = APIRouter(prefix="/v1/rlm", dependencies=[Depends(auth_dependency)])

    @router.post("/slots/{slot_slug}/workstreams/{workstream_slug}/turns")
    async def append_turn(
        slot_slug: str,
        workstream_slug: str,
        request: AppendTurnRequest,
        response: Response,
        if_match: Optional[str] = Header(default=None, alias="If-Match"),
    ) -> Dict[str, Any]:
        try:
            turn = StoredTurn(role=request.role, content=request.content)
            catalog = registry.append_turn(
                slot_slug,
                workstream_slug,
                turn,
                expected_version=_expected_version(request.expected_version, if_match),
            )
        except ValueError as exc:
            raise _mutation_error(exc) from exc
        normalized = normalized_catalog(catalog)
        response.headers["ETag"] = f'"{normalized.version}"'
        return normalized.model_dump()

    @router.delete("/slots/{slot_slug}/workstreams/{workstream_slug}")
    async def delete_workstream(
        slot_slug: str,
        workstream_slug: str,
        response: Response,
        request: Optional[DeleteWorkstreamRequest] = None,
        if_match: Optional[str] = Header(default=None, alias="If-Match"),
    ) -> Dict[str, Any]:
        try:
            catalog = registry.delete_workstream(
                slot_slug,
                workstream_slug,
                expected_version=_expected_version(
                    request.expected_version if request else None,
                    if_match,
                ),
            )
        except ValueError as exc:
            raise _mutation_error(exc) from exc
        normalized = normalized_catalog(catalog)
        response.headers["ETag"] = f'"{normalized.version}"'
        return normalized.model_dump()

    return router
