"""
@file comments.py
@brief Scenario comment endpoints — per-scenario annotations stored as JSON.

Endpoints:
  GET  /api/scenarios/{scenario_id}/comments  — list all comments for a scenario
  POST /api/scenarios/{scenario_id}/comments  — add a comment
  DELETE /api/scenarios/{scenario_id}/comments/{comment_id}  — delete a comment
"""
import json, logging, os, uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)
router = APIRouter()

class CommentIn(BaseModel):
    text: str
    author: str = "User"

class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str; text: str; author: str; created_at: str

def _comments_path(root: str, scenario_id: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in scenario_id)
    return os.path.join(root, "data", "comments", f"{safe}.json")

def _load(path: str) -> list[dict]:
    if not os.path.exists(path): return []
    with open(path) as f: return json.load(f)

def _save(path: str, data: list[dict]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f: json.dump(data, f, indent=2)

@router.get("/scenarios/{scenario_id}/comments", response_model=list[CommentOut])
def list_comments(scenario_id: str, request: Request) -> list[CommentOut]:
    """@brief List all comments for a scenario."""
    root = getattr(request.app.state, "project_root", ".")
    data = _load(_comments_path(root, scenario_id))
    return [CommentOut(**c) for c in data]

@router.post("/scenarios/{scenario_id}/comments", response_model=CommentOut)
def add_comment(scenario_id: str, body: CommentIn, request: Request) -> CommentOut:
    """@brief Add a comment to a scenario."""
    root = getattr(request.app.state, "project_root", ".")
    path = _comments_path(root, scenario_id)
    data = _load(path)
    comment = {
        "id": str(uuid.uuid4())[:8],
        "text": body.text,
        "author": body.author,
        "created_at": datetime.utcnow().isoformat()
    }
    data.append(comment)
    _save(path, data)
    return CommentOut(**comment)

@router.delete("/scenarios/{scenario_id}/comments/{comment_id}")
def delete_comment(scenario_id: str, comment_id: str, request: Request) -> dict:
    """@brief Delete a comment by ID."""
    root = getattr(request.app.state, "project_root", ".")
    path = _comments_path(root, scenario_id)
    data = _load(path)
    new_data = [c for c in data if c["id"] != comment_id]
    if len(new_data) == len(data):
        raise HTTPException(status_code=404, detail="Comment not found")
    _save(path, new_data)
    return {"success": True}
