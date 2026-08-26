"""
@file sync.py
@brief Google Drive sync routes using OAuth2 Device Authorization Grant (RFC 8628).

Device flow is appropriate for self-hosted HA add-ons because it requires no
redirect URL. The user authorises on their phone or PC; the add-on polls for
the token.

Setup (one-time):
  1. Google Cloud Console → create a project.
  2. Enable Google Drive API.
  3. Create credentials: OAuth 2.0 → TVs and Limited Input devices.
  4. Note the client_id and client_secret.
  5. Paste both into LifeLedger Settings → Google Drive.

Endpoints
---------
GET  /api/sync/status             — connected | disconnected + last sync time
POST /api/sync/drive/auth/start   — request device code from Google
POST /api/sync/drive/auth/poll    — exchange device code for refresh token
DELETE /api/sync/drive/auth       — revoke and delete stored credentials
POST /api/sync/drive/upload       — upload a file (YAML or PDF) to Drive
POST /api/sync/push               — sync all scenario YAMLs to Drive

@author  LifeLedger
@version 0.2.0
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)
router = APIRouter()

# ─────────────────────────────────────────────────────────────────────────────
# Google OAuth2 constants
# ─────────────────────────────────────────────────────────────────────────────

_DEVICE_CODE_URL = "https://oauth2.googleapis.com/device/code"
_TOKEN_URL       = "https://oauth2.googleapis.com/token"
_REVOKE_URL      = "https://oauth2.googleapis.com/revoke"
_DRIVE_SCOPE     = "https://www.googleapis.com/auth/drive.file"
_DRIVE_FILES_URL = "https://www.googleapis.com/upload/drive/v3/files"
_GRANT_TYPE      = "urn:ietf:params:oauth:grant-type:device_code"


# ─────────────────────────────────────────────────────────────────────────────
# SQLite credential storage
# ─────────────────────────────────────────────────────────────────────────────

def _db_path(request: Request) -> str:
    """@brief Resolve path to the SQLite database."""
    root = getattr(request.app.state, "project_root", ".")
    return os.environ.get(
        "LIFELEDGER_DB",
        os.path.join(root, "data", "lifeledger.db"),
    )


def _init_table(db: str) -> None:
    """@brief Ensure the drive_credentials table exists."""
    conn = sqlite3.connect(db)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS drive_credentials (
            key   TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS drive_sync_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            synced_at  TEXT,
            file_name  TEXT,
            drive_id   TEXT,
            status     TEXT
        )
    """)
    conn.commit()
    conn.close()


def _store(db: str, key: str, value: str) -> None:
    """@brief Upsert a key-value pair in drive_credentials."""
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT OR REPLACE INTO drive_credentials(key, value) VALUES (?,?)",
        (key, value),
    )
    conn.commit()
    conn.close()


def _fetch(db: str, key: str) -> Optional[str]:
    """@brief Retrieve a value from drive_credentials."""
    if not os.path.exists(db):
        return None
    conn = sqlite3.connect(db)
    row  = conn.execute(
        "SELECT value FROM drive_credentials WHERE key=?", (key,)
    ).fetchone()
    conn.close()
    return row[0] if row else None


def _delete(db: str, key: str) -> None:
    conn = sqlite3.connect(db)
    conn.execute("DELETE FROM drive_credentials WHERE key=?", (key,))
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Google API helpers
# ─────────────────────────────────────────────────────────────────────────────

def _google_post(url: str, data: dict, headers: Optional[dict] = None) -> dict:
    """
    @brief Make a POST to a Google API endpoint and return the JSON response.

    @param url      Endpoint URL.
    @param data     Form-encoded POST body dict.
    @param headers  Optional extra headers.
    @return         Parsed JSON response dict.
    @raises HTTPException  On network errors or non-200 responses.
    """
    body    = urllib.parse.urlencode(data).encode()
    req_hdr = {"Content-Type": "application/x-www-form-urlencoded"}
    if headers:
        req_hdr.update(headers)
    req = urllib.request.Request(url, data=body, headers=req_hdr, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode(errors="replace")
        logger.warning("_google_post %s → %d: %s", url, exc.code, body_text[:200])
        try:
            return json.loads(body_text)
        except Exception:
            raise HTTPException(status_code=502, detail=f"Google API error {exc.code}: {body_text[:200]}")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Network error: {exc}")


def _get_access_token(db: str) -> str:
    """
    @brief Exchange the stored refresh token for a short-lived access token.

    @param db  Path to the SQLite database.
    @return    Access token string.
    @raises HTTPException  If not connected or token refresh fails.
    """
    client_id     = _fetch(db, "client_id")
    client_secret = _fetch(db, "client_secret")
    refresh_token = _fetch(db, "refresh_token")
    if not all([client_id, client_secret, refresh_token]):
        raise HTTPException(status_code=401, detail="Google Drive not connected")
    resp = _google_post(_TOKEN_URL, {
        "client_id":     client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type":    "refresh_token",
    })
    if "access_token" not in resp:
        raise HTTPException(status_code=401, detail=f"Token refresh failed: {resp.get('error_description', resp)}")
    return resp["access_token"]


# ─────────────────────────────────────────────────────────────────────────────
# Response models
# ─────────────────────────────────────────────────────────────────────────────

class SyncStatusResponse(BaseModel):
    """@brief Response for GET /api/sync/status."""
    model_config = ConfigDict(from_attributes=True)
    connected:     bool  = False
    message:       str   = ""
    last_sync_at:  str   = ""
    conflict_status: str = "none"


class DriveAuthStartRequest(BaseModel):
    """@brief Body for POST /api/sync/drive/auth/start."""
    client_id:     str
    client_secret: str


class DriveAuthStartResponse(BaseModel):
    """
    @brief Response for POST /api/sync/drive/auth/start.

    @param device_code       Opaque code to poll with.
    @param user_code         Short code the user enters at verification_url.
    @param verification_url  URL the user visits to authorise.
    @param expires_in        Seconds until the device code expires.
    @param interval          Minimum seconds between poll attempts.
    """
    model_config = ConfigDict(from_attributes=True)
    device_code:      str
    user_code:        str
    verification_url: str
    expires_in:       int
    interval:         int


class DriveAuthPollRequest(BaseModel):
    """@brief Body for POST /api/sync/drive/auth/poll."""
    client_id:     str
    client_secret: str
    device_code:   str


class DriveAuthPollResponse(BaseModel):
    """
    @brief Response for POST /api/sync/drive/auth/poll.

    @param status   'approved' | 'pending' | 'expired' | 'error'.
    @param message  Human-readable status description.
    """
    model_config = ConfigDict(from_attributes=True)
    status:  str
    message: str = ""


class DriveUploadRequest(BaseModel):
    """@brief Body for POST /api/sync/drive/upload."""
    file_path:   str
    folder_name: str = "LifeLedger"
    mime_type:   str = "application/x-yaml"


class DriveUploadResponse(BaseModel):
    """@brief Response for POST /api/sync/drive/upload."""
    model_config = ConfigDict(from_attributes=True)
    drive_file_id: str
    drive_url:     str
    file_name:     str


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/sync/status", response_model=SyncStatusResponse)
def sync_status(request: Request) -> SyncStatusResponse:
    """
    @brief Return current Google Drive sync status.

    @return  SyncStatusResponse — connected:true if a refresh token is stored.
    """
    try:
        db = _db_path(request)
        _init_table(db)
        has_token = bool(_fetch(db, "refresh_token"))
        if has_token:
            # Try to read last sync time
            conn     = sqlite3.connect(db)
            row      = conn.execute(
                "SELECT synced_at FROM drive_sync_log ORDER BY id DESC LIMIT 1"
            ).fetchone()
            conn.close()
            last_sync = row[0] if row else ""
            return SyncStatusResponse(
                connected=True,
                message="Google Drive connected",
                last_sync_at=last_sync,
            )
    except Exception as exc:
        logger.debug("sync_status: %s", exc)
    return SyncStatusResponse(
        connected=False,
        message="Google Drive not connected",
    )


@router.post("/sync/drive/auth/start", response_model=DriveAuthStartResponse)
def drive_auth_start(request: Request, body: DriveAuthStartRequest) -> DriveAuthStartResponse:
    """
    @brief Request a device code from Google OAuth2.

    The user must visit verification_url and enter user_code to authorise
    the connection. Then poll /api/sync/drive/auth/poll until approved.

    @param body  DriveAuthStartRequest with client_id and client_secret.
    @return      DriveAuthStartResponse with codes and verification URL.
    """
    logger.info("drive_auth_start: requesting device code")
    resp = _google_post(_DEVICE_CODE_URL, {
        "client_id": body.client_id,
        "scope":     _DRIVE_SCOPE,
    })
    if "device_code" not in resp:
        error = resp.get("error_description") or resp.get("error") or str(resp)
        raise HTTPException(status_code=400, detail=f"Google returned: {error}")

    # Temporarily store credentials (will be confirmed on poll success)
    db = _db_path(request)
    _init_table(db)
    _store(db, "pending_client_id",     body.client_id)
    _store(db, "pending_client_secret", body.client_secret)

    return DriveAuthStartResponse(
        device_code=resp["device_code"],
        user_code=resp["user_code"],
        verification_url=resp.get("verification_url", "https://google.com/device"),
        expires_in=int(resp.get("expires_in", 1800)),
        interval=int(resp.get("interval", 5)),
    )


@router.post("/sync/drive/auth/poll", response_model=DriveAuthPollResponse)
def drive_auth_poll(request: Request, body: DriveAuthPollRequest) -> DriveAuthPollResponse:
    """
    @brief Poll Google for the OAuth2 token after the user has authorised.

    Call this every `interval` seconds after drive_auth_start. Returns
    'pending' until the user approves, then 'approved' with the token stored.

    @param body  DriveAuthPollRequest with client credentials and device code.
    @return      DriveAuthPollResponse with status 'approved' | 'pending' | 'expired' | 'error'.
    """
    resp = _google_post(_TOKEN_URL, {
        "client_id":     body.client_id,
        "client_secret": body.client_secret,
        "device_code":   body.device_code,
        "grant_type":    _GRANT_TYPE,
    })
    error = resp.get("error", "")
    if error == "authorization_pending":
        return DriveAuthPollResponse(status="pending", message="Waiting for user authorisation")
    if error == "slow_down":
        return DriveAuthPollResponse(status="pending", message="Polling too fast — wait longer")
    if error in ("expired_token", "access_denied"):
        return DriveAuthPollResponse(status=error, message=resp.get("error_description", error))
    if error:
        return DriveAuthPollResponse(status="error", message=resp.get("error_description", error))

    # Success — store credentials
    refresh_token = resp.get("refresh_token", "")
    if not refresh_token:
        return DriveAuthPollResponse(status="error", message="No refresh token in response")

    db = _db_path(request)
    _init_table(db)
    _store(db, "client_id",     body.client_id)
    _store(db, "client_secret", body.client_secret)
    _store(db, "refresh_token", refresh_token)
    _delete(db, "pending_client_id")
    _delete(db, "pending_client_secret")
    logger.info("drive_auth_poll: Google Drive connected successfully")
    return DriveAuthPollResponse(status="approved", message="Google Drive connected successfully")


@router.delete("/sync/drive/auth")
def drive_auth_revoke(request: Request) -> dict:
    """
    @brief Revoke and delete stored Google Drive credentials.

    @return  {'success': True}.
    """
    db = _db_path(request)
    token = _fetch(db, "refresh_token")
    if token:
        try:
            client_id     = _fetch(db, "client_id") or ""
            client_secret = _fetch(db, "client_secret") or ""
            _google_post(_REVOKE_URL, {"token": token})
        except Exception as exc:
            logger.warning("drive_auth_revoke: revoke call failed (proceeding): %s", exc)
    for key in ("client_id", "client_secret", "refresh_token"):
        _delete(db, key)
    logger.info("drive_auth_revoke: credentials removed")
    return {"success": True, "message": "Google Drive disconnected"}


@router.post("/sync/drive/upload", response_model=DriveUploadResponse)
def drive_upload(request: Request, body: DriveUploadRequest) -> DriveUploadResponse:
    """
    @brief Upload a file to Google Drive (Drive.file scope — app folder only).

    @param body  DriveUploadRequest with local file path and optional folder name.
    @return      DriveUploadResponse with Drive file ID and web URL.
    @raises HTTPException  If not connected or the file does not exist.
    """
    root      = getattr(request.app.state, "project_root", ".")
    abs_path  = body.file_path if os.path.isabs(body.file_path) \
                else os.path.join(root, body.file_path)
    if not os.path.exists(abs_path):
        raise HTTPException(status_code=404, detail=f"File not found: {body.file_path}")

    db           = _db_path(request)
    access_token = _get_access_token(db)
    file_name    = os.path.basename(abs_path)

    with open(abs_path, "rb") as fh:
        file_bytes = fh.read()

    # Multipart upload
    boundary = "LifeLedger_boundary_xyz"
    metadata = json.dumps({"name": file_name}).encode()
    body_parts = (
        f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode()
        + metadata
        + f"\r\n--{boundary}\r\nContent-Type: {body.mime_type}\r\n\r\n".encode()
        + file_bytes
        + f"\r\n--{boundary}--".encode()
    )
    upload_req = urllib.request.Request(
        f"{_DRIVE_FILES_URL}?uploadType=multipart",
        data=body_parts,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type":  f"multipart/related; boundary={boundary}",
            "Content-Length": str(len(body_parts)),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(upload_req, timeout=60) as r:
            result = json.loads(r.read())
    except urllib.error.HTTPError as exc:
        err = exc.read().decode(errors="replace")
        raise HTTPException(status_code=502, detail=f"Drive upload failed: {err[:200]}")

    drive_id = result.get("id", "")
    web_url  = f"https://drive.google.com/file/d/{drive_id}/view"

    # Log the sync
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO drive_sync_log(synced_at, file_name, drive_id, status) VALUES(?,?,?,?)",
        (datetime.utcnow().isoformat(), file_name, drive_id, "success"),
    )
    conn.commit()
    conn.close()
    logger.info("drive_upload: %s → %s", file_name, drive_id)
    return DriveUploadResponse(drive_file_id=drive_id, drive_url=web_url, file_name=file_name)


@router.post("/sync/push")
def sync_push(request: Request) -> dict:
    """
    @brief Push all scenario YAMLs to Google Drive.

    @return  {'synced': [list of file names uploaded]}.
    """
    root    = getattr(request.app.state, "project_root", ".")
    sc_dir  = os.path.join(root, "data", "scenarios")
    db      = _db_path(request)
    synced: list[str] = []
    errors: list[str] = []

    if not os.path.isdir(sc_dir):
        raise HTTPException(status_code=404, detail="Scenarios directory not found")

    for fname in os.listdir(sc_dir):
        if not fname.endswith(".yaml"):
            continue
        try:
            local = os.path.join(sc_dir, fname)
            drive_upload(request, DriveUploadRequest(
                file_path=local, folder_name="LifeLedger/scenarios",
            ))
            synced.append(fname)
        except Exception as exc:
            errors.append(f"{fname}: {exc}")
            logger.error("sync_push: %s", exc)

    return {"synced": synced, "errors": errors}


@router.post("/sync/pull")
def sync_pull(request: Request) -> dict:
    """
    @brief Pull is not implemented — LifeLedger is the source of truth.

    @return  501 Not Implemented.
    """
    raise HTTPException(
        status_code=501,
        detail="Pull sync is not implemented. LifeLedger is the source of truth.",
    )
