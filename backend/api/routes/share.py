"""
@file share.py
@brief Read-only scenario share links.

POST /api/scenarios/share  — create a share token (returns URL)
GET  /api/share/{token}    — read-only scenario data (no auth required)
DELETE /api/share/{token}  — revoke a share link
"""
import json, logging, os, sqlite3, uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from backend.persistence.yaml_serialiser import load_yaml

logger = logging.getLogger(__name__)
router = APIRouter()

class ShareRequest(BaseModel):
    scenario_path: str
    label: str = ""

class ShareResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    token: str; url: str; scenario_path: str; label: str; created_at: str

def _db(request: Request) -> str:
    root = getattr(request.app.state, "project_root", ".")
    return os.environ.get("LIFELEDGER_DB", os.path.join(root, "data", "lifeledger.db"))

def _init(db: str) -> None:
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE IF NOT EXISTS share_tokens (
        token TEXT PRIMARY KEY, scenario_path TEXT,
        label TEXT, created_at TEXT
    )""")
    conn.commit(); conn.close()

@router.post("/scenarios/share", response_model=ShareResponse)
def create_share(request: Request, body: ShareRequest) -> ShareResponse:
    """@brief Generate a read-only share token for a scenario."""
    root = getattr(request.app.state, "project_root", ".")
    abs_path = body.scenario_path if os.path.isabs(body.scenario_path)                else os.path.join(root, body.scenario_path)
    if not os.path.exists(abs_path):
        raise HTTPException(status_code=404, detail="Scenario not found")
    token = str(uuid.uuid4()).replace("-","")[:24]
    db    = _db(request); _init(db)
    now   = datetime.utcnow().isoformat()
    conn  = sqlite3.connect(db)
    conn.execute("INSERT INTO share_tokens VALUES(?,?,?,?)",
                 (token, body.scenario_path, body.label, now))
    conn.commit(); conn.close()
    # Build URL using ingress path if available
    base_url = str(request.base_url).rstrip("/")
    url = f"{base_url}/api/share/{token}"
    logger.info("create_share: %s → %s", body.scenario_path, token[:8])
    return ShareResponse(token=token, url=url, scenario_path=body.scenario_path,
                         label=body.label, created_at=now)

@router.get("/share/{token}")
def read_share(token: str, request: Request) -> dict:
    """@brief Return read-only scenario data for a share token."""
    db = _db(request); _init(db)
    conn = sqlite3.connect(db); conn.row_factory = sqlite3.Row
    row  = conn.execute("SELECT * FROM share_tokens WHERE token=?", (token,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Share link not found or expired")
    root     = getattr(request.app.state, "project_root", ".")
    abs_path = row["scenario_path"] if os.path.isabs(row["scenario_path"])                else os.path.join(root, row["scenario_path"])
    if not os.path.exists(abs_path):
        raise HTTPException(status_code=410, detail="Scenario file no longer exists")
    raw = load_yaml(abs_path)
    return {"scenario": raw.get("scenario", raw), "label": row["label"],
            "shared_at": row["created_at"], "readonly": True}

@router.get("/scenarios/shares")
def list_shares(request: Request) -> list[dict]:
    """@brief List all active share tokens."""
    db = _db(request); _init(db)
    conn = sqlite3.connect(db); conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT token, scenario_path, label, created_at FROM share_tokens").fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.delete("/share/{token}")
def revoke_share(token: str, request: Request) -> dict:
    """@brief Revoke a share link."""
    db = _db(request); _init(db)
    conn = sqlite3.connect(db)
    conn.execute("DELETE FROM share_tokens WHERE token=?", (token,))
    conn.commit(); conn.close()
    return {"success": True}
