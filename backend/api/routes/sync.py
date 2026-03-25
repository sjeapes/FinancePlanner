"""
@file sync.py
@brief FastAPI stub routes for Google Drive sync (Phase 2 placeholder).

Real sync implementation is deferred to Phase 3. These endpoints signal
their stub status clearly in the response body.

Endpoints:
  GET  /api/sync/status — returns sync disabled message
  POST /api/sync/push   — 501 Not Implemented
  POST /api/sync/pull   — 501 Not Implemented
"""

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Response models ───────────────────────────────────────────────────────────

class SyncStatusResponse(BaseModel):
    """
    @brief Response for GET /api/sync/status.
    @param enabled Whether sync is enabled.
    @param message Human-readable status message.
    @param last_sync_at ISO timestamp of last sync, or None.
    @param conflict_status Current conflict status string.
    """
    model_config = ConfigDict(from_attributes=True)

    enabled: bool = False
    message: str = ""
    last_sync_at: str = ""
    conflict_status: str = "none"


# ── Route handlers ────────────────────────────────────────────────────────────

@router.get("/sync/status", response_model=SyncStatusResponse)
def sync_status(request: Request) -> SyncStatusResponse:
    """
    @brief Return current Google Drive sync status.

    Phase 2 stub — always returns disabled. Phase 3 will implement
    real OAuth2 sync with conflict detection.

    @param request FastAPI Request.
    @return SyncStatusResponse indicating sync is not yet configured.
    """
    try:
        from backend.persistence.sqlite_cache import get_sync_state

        engine = getattr(request.app.state, "db_engine", None)
        if engine:
            state = get_sync_state(engine)
            if state and state.get("last_sync_at"):
                last_sync = str(state["last_sync_at"])
                conflict = state.get("conflict_status", "none")
                return SyncStatusResponse(
                    enabled=False,
                    message="Google Drive sync not yet configured",
                    last_sync_at=last_sync,
                    conflict_status=conflict,
                )
    except Exception as exc:
        logger.debug("sync_status: could not read sync state: %s", exc)

    return SyncStatusResponse(
        enabled=False,
        message="Google Drive sync not yet configured",
        last_sync_at="",
        conflict_status="none",
    )


@router.post("/sync/push")
def sync_push(request: Request) -> None:
    """
    @brief Push local data to Google Drive (not yet implemented).

    This endpoint will be implemented in Phase 3 with full OAuth2 PKCE
    authentication and conflict resolution.

    @param request FastAPI Request.
    """
    logger.info("sync_push: called — Phase 3 stub")
    raise HTTPException(
        status_code=501,
        detail={
            "error": "Not Implemented",
            "detail": "Google Drive sync push will be implemented in Phase 3.",
        },
    )


@router.post("/sync/pull")
def sync_pull(request: Request) -> None:
    """
    @brief Pull data from Google Drive (not yet implemented).

    This endpoint will be implemented in Phase 3 with full conflict detection
    (SHA-256 hash comparison) and configurable resolution strategies.

    @param request FastAPI Request.
    """
    logger.info("sync_pull: called — Phase 3 stub")
    raise HTTPException(
        status_code=501,
        detail={
            "error": "Not Implemented",
            "detail": "Google Drive sync pull will be implemented in Phase 3.",
        },
    )
