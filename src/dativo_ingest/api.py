"""FastAPI application exposing AI context metadata for agents."""

from __future__ import annotations

import os
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, status

from .metadata_store import load_asset_metadata

app = FastAPI(
    title="Dativo Metadata API",
    version="1.0.0",
    description="Policy-guarded metadata API for AI agents. Provides ODCS-aligned context without exposing raw data.",
)


def authorize(authorization: Optional[str] = Header(None)) -> bool:
    """Simple bearer-token authorization guard."""
    token = os.getenv("AI_CONTEXT_API_TOKEN")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI context API token is not configured",
        )

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )

    provided = authorization.split(" ", 1)[1].strip()
    if provided != token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid bearer token",
        )
    return True


@app.get("/api/v1/metadata/ai_context", summary="Fetch AI-ready metadata context for an asset")
def get_ai_context(asset_name: str, _: bool = Depends(authorize)) -> dict:
    """Return schema, governance, lineage, and FinOps context for a given asset."""
    try:
        payload = load_asset_metadata(asset_name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    asset = payload.get("asset", {})
    metrics = payload.get("metrics", {})
    compliance = asset.get("compliance") or {}
    team = asset.get("team") or {}

    response = {
        "asset_name": asset.get("name"),
        "version": asset.get("version"),
        "domain": asset.get("domain"),
        "data_product": asset.get("dataProduct"),
        "status": asset.get("status"),
        "schema": asset.get("schema", []),
        "classification": compliance.get("classification", []),
        "governance": {
            "owner": team.get("owner"),
            "cost_center": team.get("cost_center"),
            "retention_days": compliance.get("retention_days"),
            "regulations": compliance.get("regulations", []),
        },
        "lineage": metrics.get("lineage") or asset.get("lineage", []),
        "validation_status": metrics.get("validation_status"),
        "finops": metrics.get("finops"),
        "audit": asset.get("audit", []),
        "last_updated_at": metrics.get("timestamp"),
        "metadata_source": metrics.get("metadata_source"),
    }
    return response


__all__ = ["app"]
