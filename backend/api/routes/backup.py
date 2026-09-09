"""
@file backup.py
@brief FastAPI routes for full-application data export and import ("backup / restore").

This module bundles everything a user has entered into LifeLedger — every
scenario YAML, checkpoints, scenario comments, generated report output, the
whole `config/` directory, and (optionally) the SQLite database holding
share links, sync state, cached market prices and encrypted API keys — into
a single downloadable ZIP archive, and can restore that archive back onto a
fresh install.

Endpoints
---------
GET  /api/backup/export
    Stream a ZIP archive of all user data for download.

POST /api/backup/import
    Upload a previously exported ZIP archive and restore it. A safety
    backup of the current state is always written first (see
    `backup.backup_dir` in lifeledger_config.yaml) so an import can be
    undone by re-importing the pre-import snapshot.

GET  /api/backup/list
    List locally-retained pre-import safety backups.

All behaviour (which folders are bundled, whether the database/API keys are
included, how many safety backups are retained, and whether app-version
mismatches block an import) is controlled by the `backup:` section of
`config/lifeledger_config.yaml` — see that file for the full option list.

@author  LifeLedger
@version 0.1.0
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()

MANIFEST_NAME = "manifest.json"
DB_ARCHIVE_NAME = "data/lifeledger.db"
MAX_UPLOAD_BYTES = 200 * 1024 * 1024   # 200 MB — generous ceiling for a full backup


# ─────────────────────────────────────────────────────────────────────────────
# Config helpers
# ─────────────────────────────────────────────────────────────────────────────


def _backup_cfg(request: Request) -> dict[str, Any]:
    """
    @brief Read the `backup:` section of lifeledger_config.yaml, with safe defaults.

    @param request  FastAPI request (used to reach app.state.config).
    @return         Dict of backup settings.
    """
    defaults = {
        "include_paths": ["config", "data/scenarios", "data/checkpoints", "data/comments", "data/reports_output"],
        "include_database": True,
        "include_api_keys_in_export": False,
        "max_backups_retained": 10,
        "backup_dir": "data/backups",
        "enforce_version_match": False,
    }
    try:
        raw = getattr(request.app.state.config, "raw", {}) or {}
        cfg = {**defaults, **(raw.get("backup") or {})}
        return cfg
    except Exception as exc:
        logger.warning("_backup_cfg: falling back to defaults (%s)", exc)
        return defaults


def _app_version(request: Request) -> str:
    """@brief Return the running app's version string from config, or 'unknown'."""
    try:
        raw = getattr(request.app.state.config, "raw", {}) or {}
        return str(raw.get("app", {}).get("version", "unknown"))
    except Exception:
        return "unknown"


# ─────────────────────────────────────────────────────────────────────────────
# Export
# ─────────────────────────────────────────────────────────────────────────────


def _build_export_zip(request: Request, dest_path: str, cfg: dict[str, Any]) -> dict[str, Any]:
    """
    @brief Build a full backup ZIP at dest_path.

    @param request    FastAPI request (for project_root / db_path).
    @param dest_path  Filesystem path to write the ZIP to.
    @param cfg        Backup config dict (see `_backup_cfg`).
    @return           Manifest dict written into the archive.
    """
    root = getattr(request.app.state, "project_root", ".")
    manifest: dict[str, Any] = {
        "app": "LifeLedger",
        "app_version": _app_version(request),
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "include_paths": [],
        "include_database": False,
        "include_api_keys": False,
    }

    with zipfile.ZipFile(dest_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # ── Plain file/folder paths (YAML/JSON user data + config) ──────────
        for rel in cfg.get("include_paths", []):
            abs_path = os.path.join(root, rel)
            if not os.path.exists(abs_path):
                continue
            manifest["include_paths"].append(rel)
            if os.path.isfile(abs_path):
                zf.write(abs_path, arcname=rel)
                continue
            for dirpath, _dirs, files in os.walk(abs_path):
                for fname in files:
                    fp = os.path.join(dirpath, fname)
                    arcname = os.path.relpath(fp, root)
                    zf.write(fp, arcname=arcname)

        # ── SQLite database (optionally stripped of API keys) ───────────────
        if cfg.get("include_database", True):
            db_path = getattr(request.app.state, "db_path", None) or os.path.join(root, "data", "lifeledger.db")
            if os.path.exists(db_path):
                manifest["include_database"] = True
                manifest["include_api_keys"] = bool(cfg.get("include_api_keys_in_export", False))
                _write_db_snapshot(zf, db_path, strip_api_keys=not manifest["include_api_keys"])

        zf.writestr(MANIFEST_NAME, json.dumps(manifest, indent=2))

    logger.info(
        "_build_export_zip: wrote %s (%d paths, db=%s, api_keys=%s)",
        dest_path, len(manifest["include_paths"]), manifest["include_database"], manifest["include_api_keys"],
    )
    return manifest


def _write_db_snapshot(zf: zipfile.ZipFile, db_path: str, strip_api_keys: bool) -> None:
    """
    @brief Safely snapshot the live SQLite database into the archive.

    Uses SQLite's own backup API (via a temp file) so the export is
    consistent even while the API is actively reading/writing the DB, then
    optionally strips the api_keys table's *contents* (keeping the table
    schema intact) before adding it to the archive.

    @param zf              Open ZipFile to write into.
    @param db_path         Path to the live database file.
    @param strip_api_keys  If True, clear the api_keys table in the snapshot.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        src = sqlite3.connect(db_path)
        dst = sqlite3.connect(tmp_path)
        with dst:
            src.backup(dst)
        src.close()

        if strip_api_keys:
            try:
                cur = dst.cursor()
                cur.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='api_keys'"
                )
                if cur.fetchone():
                    cur.execute("DELETE FROM api_keys")
                    dst.commit()
            except Exception as exc:
                logger.warning("_write_db_snapshot: could not strip api_keys: %s", exc)
        dst.close()

        zf.write(tmp_path, arcname=DB_ARCHIVE_NAME)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _prune_backups(backup_dir: str, keep: int) -> None:
    """
    @brief Delete oldest pre-import safety backups beyond the retention limit.

    @param backup_dir  Directory containing timestamped backup ZIPs.
    @param keep         Number of most-recent backups to retain.
    """
    if not os.path.isdir(backup_dir):
        return
    files = sorted(
        (os.path.join(backup_dir, f) for f in os.listdir(backup_dir) if f.endswith(".zip")),
        key=os.path.getmtime,
    )
    for old in files[:-keep] if keep > 0 else files:
        try:
            os.remove(old)
            logger.info("_prune_backups: removed old backup %s", old)
        except OSError as exc:
            logger.warning("_prune_backups: failed to remove %s: %s", old, exc)


@router.get("/backup/export")
async def export_backup(request: Request) -> StreamingResponse:
    """
    @brief Export all user data (scenarios, checkpoints, comments, config,
           and optionally the database) as a downloadable ZIP archive.

    @param request  FastAPI request.
    @return         StreamingResponse with the ZIP file.
    """
    cfg = _backup_cfg(request)
    try:
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp_path = tmp.name
        _build_export_zip(request, tmp_path, cfg)

        def _iterfile():
            try:
                with open(tmp_path, "rb") as f:
                    while chunk := f.read(1024 * 1024):
                        yield chunk
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"lifeledger_backup_{stamp}.zip"
        return StreamingResponse(
            _iterfile(),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as exc:
        logger.error("export_backup error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Export failed: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# Import
# ─────────────────────────────────────────────────────────────────────────────


class ImportBackupResponse(BaseModel):
    """@brief Result of a backup import."""
    success: bool
    message: str
    safety_backup: Optional[str] = None
    restored_paths: list[str] = []
    restored_database: bool = False
    warnings: list[str] = []


def _merge_database(live_db_path: str, imported_db_path: str, skip_tables: Optional[set[str]] = None) -> list[str]:
    """
    @brief Merge an imported SQLite database's tables into the live database.

    For each table present in the imported DB, replaces the live table's
    contents wholesale (DELETE + INSERT) inside a single transaction via
    SQLite's ATTACH DATABASE, so the live connection never has to be closed
    or the file swapped out from under the running app.

    @param live_db_path      Path to the currently-running database.
    @param imported_db_path  Path to the extracted database from the archive.
    @param skip_tables       Table names to leave untouched in the live DB —
                              used to protect existing API keys when the
                              archive was exported with them stripped (an
                              empty api_keys table in the archive must NOT
                              be allowed to wipe real keys already in place).
    @return                  List of table names that were merged.
    """
    skip_tables = skip_tables or set()
    conn = sqlite3.connect(live_db_path)
    merged: list[str] = []
    try:
        conn.execute("ATTACH DATABASE ? AS imported", (imported_db_path,))
        cur = conn.execute("SELECT name FROM imported.sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur.fetchall() if not r[0].startswith("sqlite_")]
        with conn:
            for table in tables:
                if table in skip_tables:
                    logger.info("_merge_database: skipping protected table '%s'", table)
                    continue
                # Only merge tables that also exist in the live schema, to
                # avoid importing an incompatible/future schema wholesale.
                exists = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
                ).fetchone()
                if not exists:
                    logger.warning("_merge_database: skipping unknown table '%s'", table)
                    continue
                conn.execute(f"DELETE FROM main.{table}")
                conn.execute(f"INSERT INTO main.{table} SELECT * FROM imported.{table}")
                merged.append(table)
        conn.execute("DETACH DATABASE imported")
    finally:
        conn.close()
    return merged


@router.post("/backup/import", response_model=ImportBackupResponse)
async def import_backup(
    request: Request,
    file: UploadFile = File(...),
) -> ImportBackupResponse:
    """
    @brief Restore all user data from a previously exported ZIP archive.

    Always writes a pre-import safety backup of the current state first
    (retained per `backup.max_backups_retained`), then overwrites the
    configured data/config paths and merges the database tables found in
    the archive.

    @param request  FastAPI request.
    @param file     Uploaded ZIP archive (from /api/backup/export).
    @return         ImportBackupResponse summarising what was restored.
    """
    warnings: list[str] = []
    root = getattr(request.app.state, "project_root", ".")
    cfg = _backup_cfg(request)

    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large (max {MAX_UPLOAD_BYTES // 1024 // 1024} MB)")
    if len(raw) == 0:
        raise HTTPException(status_code=400, detail="Empty file uploaded")

    with tempfile.TemporaryDirectory() as tmp_dir:
        upload_path = os.path.join(tmp_dir, "upload.zip")
        with open(upload_path, "wb") as f:
            f.write(raw)

        try:
            zf = zipfile.ZipFile(upload_path)
        except zipfile.BadZipFile:
            raise HTTPException(status_code=422, detail="Not a valid ZIP archive")

        names = zf.namelist()
        if MANIFEST_NAME not in names:
            raise HTTPException(status_code=422, detail="Archive is missing manifest.json — not a LifeLedger backup")

        try:
            manifest = json.loads(zf.read(MANIFEST_NAME))
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Unreadable manifest.json: {exc}")

        current_version = _app_version(request)
        archive_version = str(manifest.get("app_version", "unknown"))
        if cfg.get("enforce_version_match") and archive_version != current_version:
            raise HTTPException(
                status_code=409,
                detail=f"Backup was made with version {archive_version}, running version is {current_version}. "
                       "Set backup.enforce_version_match: false to allow anyway.",
            )
        if archive_version != current_version:
            warnings.append(f"Backup app version ({archive_version}) differs from current ({current_version}).")

        # ── 1. Safety backup of current state before touching anything ──────
        safety_backup_name = None
        try:
            backup_dir = os.path.join(root, cfg.get("backup_dir", "data/backups"))
            os.makedirs(backup_dir, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safety_backup_name = f"pre_import_{stamp}.zip"
            _build_export_zip(request, os.path.join(backup_dir, safety_backup_name), cfg)
            _prune_backups(backup_dir, int(cfg.get("max_backups_retained", 10)))
        except Exception as exc:
            logger.error("import_backup: safety backup failed, aborting import: %s", exc, exc_info=True)
            raise HTTPException(status_code=500, detail=f"Could not create safety backup — import aborted: {exc}")

        # ── 2. Extract archive (skip manifest + db, handled separately) ─────
        extract_dir = os.path.join(tmp_dir, "extracted")
        zf.extractall(extract_dir)
        zf.close()

        restored_paths: list[str] = []
        for rel in manifest.get("include_paths", []):
            src = os.path.join(extract_dir, rel)
            dst = os.path.join(root, rel)
            if not os.path.exists(src):
                warnings.append(f"Archive claimed '{rel}' but it was missing — skipped.")
                continue
            try:
                if os.path.isdir(src):
                    if os.path.exists(dst):
                        shutil.rmtree(dst)
                    shutil.copytree(src, dst)
                else:
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copy2(src, dst)
                restored_paths.append(rel)
            except Exception as exc:
                logger.error("import_backup: failed restoring '%s': %s", rel, exc, exc_info=True)
                warnings.append(f"Failed to restore '{rel}': {exc}")

        # ── 3. Merge database tables ─────────────────────────────────────────
        restored_db = False
        db_src = os.path.join(extract_dir, DB_ARCHIVE_NAME)
        if manifest.get("include_database") and os.path.exists(db_src):
            live_db_path = getattr(request.app.state, "db_path", None) or os.path.join(root, "data", "lifeledger.db")
            try:
                skip = set() if manifest.get("include_api_keys") else {"api_keys"}
                merged_tables = _merge_database(live_db_path, db_src, skip_tables=skip)
                restored_db = True
                if not manifest.get("include_api_keys"):
                    warnings.append("Archive did not include API keys — existing keys were left untouched.")
                logger.info("import_backup: merged tables %s", merged_tables)
            except Exception as exc:
                logger.error("import_backup: database merge failed: %s", exc, exc_info=True)
                warnings.append(f"Database merge failed: {exc}")

        logger.info(
            "import_backup: restored %d paths, db=%s, safety_backup=%s",
            len(restored_paths), restored_db, safety_backup_name,
        )
        return ImportBackupResponse(
            success=True,
            message=f"Restored {len(restored_paths)} data path(s)" + (" and database" if restored_db else "") + ".",
            safety_backup=safety_backup_name,
            restored_paths=restored_paths,
            restored_database=restored_db,
            warnings=warnings,
        )


@router.get("/backup/list")
async def list_backups(request: Request) -> dict[str, Any]:
    """
    @brief List locally-retained pre-import safety backups.

    @param request  FastAPI request.
    @return         Dict with a `backups` list of {name, size_bytes, created_at}.
    """
    cfg = _backup_cfg(request)
    root = getattr(request.app.state, "project_root", ".")
    backup_dir = os.path.join(root, cfg.get("backup_dir", "data/backups"))
    out = []
    if os.path.isdir(backup_dir):
        for fname in sorted(os.listdir(backup_dir), reverse=True):
            if not fname.endswith(".zip"):
                continue
            fp = os.path.join(backup_dir, fname)
            out.append({
                "name": fname,
                "size_bytes": os.path.getsize(fp),
                "created_at": datetime.fromtimestamp(os.path.getmtime(fp)).isoformat(),
            })
    return {"backups": out}
