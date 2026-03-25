"""
@file sqlite_cache.py
@brief SQLAlchemy 2.0 models and session management for LifeLedger SQLite cache.

Provides tables for price history, API keys (base64-obfuscated), and sync state.
API keys are stored with base64 encoding as simple obfuscation; real encryption
is deferred to Phase 5.
"""

import base64
import logging
from contextlib import contextmanager
from datetime import date, datetime
from typing import Generator, Optional

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

logger = logging.getLogger(__name__)


# ── Declarative base ──────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    """
    @brief SQLAlchemy 2.0 declarative base for all LifeLedger tables.
    """
    pass


# ── Table definitions ─────────────────────────────────────────────────────────

class PriceHistory(Base):
    """
    @brief SQLAlchemy model for the price_history table.

    Stores historical and current prices fetched from market data providers.
    Historical prices are immutable once recorded.
    """

    __tablename__ = "price_history"
    __table_args__ = (
        UniqueConstraint("symbol", "date", name="uq_price_history_symbol_date"),
    )

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    symbol: str = Column(String(50), nullable=False, index=True)
    date: str = Column(String(10), nullable=False, index=True)   # ISO date string
    price: float = Column(Float, nullable=False)
    provider: str = Column(String(50), nullable=False, default="unknown")
    created_at: datetime = Column(DateTime, nullable=False, default=datetime.utcnow)


class ApiKey(Base):
    """
    @brief SQLAlchemy model for the api_keys table.

    Stores provider API keys as base64-encoded strings.
    Keys must never be stored in plain text or in YAML files.
    """

    __tablename__ = "api_keys"
    __table_args__ = (
        UniqueConstraint("provider", name="uq_api_keys_provider"),
    )

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    provider: str = Column(String(50), nullable=False, index=True)
    encrypted_key: str = Column(Text, nullable=False)  # base64 encoded
    created_at: datetime = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: datetime = Column(DateTime, nullable=False, default=datetime.utcnow)


class SyncState(Base):
    """
    @brief SQLAlchemy model for the sync_state table.

    Tracks Google Drive sync status, conflict detection, and file hashes.
    One row per sync channel (currently only 'drive').
    """

    __tablename__ = "sync_state"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    last_sync_at: Optional[datetime] = Column(DateTime, nullable=True)
    conflict_status: str = Column(String(20), nullable=False, default="none")
    local_hash: Optional[str] = Column(String(64), nullable=True)
    remote_hash: Optional[str] = Column(String(64), nullable=True)


# ── Engine and session ────────────────────────────────────────────────────────

def get_engine(db_path: str):
    """
    @brief Create and return a SQLAlchemy engine for the given SQLite path.
    @param db_path Absolute or relative path to the SQLite database file.
    @return SQLAlchemy Engine instance.
    """
    try:
        url = f"sqlite:///{db_path}"
        engine = create_engine(url, connect_args={"check_same_thread": False})
        logger.debug("get_engine: created engine for %s", db_path)
        return engine
    except Exception as exc:
        logger.error("get_engine: failed to create engine for %s: %s", db_path, exc)
        raise


@contextmanager
def get_session(engine) -> Generator[Session, None, None]:
    """
    @brief Context manager that provides a SQLAlchemy Session.

    Commits on clean exit, rolls back on exception.

    @param engine SQLAlchemy Engine instance.
    @return Generator yielding a Session object.
    """
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.error("get_session: transaction rolled back: %s", exc)
        raise
    finally:
        session.close()


def init_db(db_path: str):
    """
    @brief Initialise the SQLite database by creating all tables.

    Safe to call on every startup — uses CREATE TABLE IF NOT EXISTS semantics.

    @param db_path Path to the SQLite database file.
    @return SQLAlchemy Engine instance bound to the initialised database.
    """
    try:
        engine = get_engine(db_path)
        Base.metadata.create_all(engine)
        logger.info("init_db: all tables created/verified at %s", db_path)
        return engine
    except Exception as exc:
        logger.error("init_db: failed to initialise database at %s: %s", db_path, exc)
        raise


# ── Encoding helpers ──────────────────────────────────────────────────────────

def _encode_key(plaintext: str) -> str:
    """
    @brief Encode a plaintext API key as base64.
    @param plaintext Raw API key string.
    @return Base64-encoded string.
    """
    return base64.b64encode(plaintext.encode("utf-8")).decode("utf-8")


def _decode_key(encoded: str) -> str:
    """
    @brief Decode a base64-encoded API key back to plaintext.
    @param encoded Base64-encoded key string.
    @return Decoded plaintext string.
    """
    return base64.b64decode(encoded.encode("utf-8")).decode("utf-8")


# ── CRUD helpers ──────────────────────────────────────────────────────────────

def upsert_price(
    engine,
    symbol: str,
    price_date: date,
    price: float,
    provider: str = "unknown",
) -> bool:
    """
    @brief Insert a price record if one does not already exist for that symbol+date.

    Historical prices are immutable — existing records are never overwritten.

    @param engine SQLAlchemy Engine instance.
    @param symbol Ticker symbol string.
    @param price_date Date of the price observation.
    @param price Price value as float.
    @param provider Provider identifier string.
    @return True if inserted, False if already existed or on error.
    """
    date_str = price_date.isoformat()
    try:
        with get_session(engine) as session:
            existing = session.execute(
                select(PriceHistory).where(
                    PriceHistory.symbol == symbol,
                    PriceHistory.date == date_str,
                )
            ).scalar_one_or_none()

            if existing is not None:
                logger.debug(
                    "upsert_price: %s on %s already cached — skipping", symbol, date_str
                )
                return False

            record = PriceHistory(
                symbol=symbol,
                date=date_str,
                price=price,
                provider=provider,
                created_at=datetime.utcnow(),
            )
            session.add(record)
            logger.debug("upsert_price: cached %s on %s = %.4f (%s)", symbol, date_str, price, provider)
            return True
    except Exception as exc:
        logger.error("upsert_price: error for %s on %s: %s", symbol, date_str, exc)
        return False


def get_prices(
    engine,
    symbol: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> list[dict]:
    """
    @brief Retrieve cached price records for a symbol within an optional date range.
    @param engine SQLAlchemy Engine instance.
    @param symbol Ticker symbol string.
    @param start_date Inclusive start date filter; None = no lower bound.
    @param end_date Inclusive end date filter; None = no upper bound.
    @return List of dicts with keys: symbol, date, price, provider.
    """
    try:
        with get_session(engine) as session:
            stmt = select(PriceHistory).where(PriceHistory.symbol == symbol)
            if start_date:
                stmt = stmt.where(PriceHistory.date >= start_date.isoformat())
            if end_date:
                stmt = stmt.where(PriceHistory.date <= end_date.isoformat())
            stmt = stmt.order_by(PriceHistory.date)
            rows = session.execute(stmt).scalars().all()
            return [
                {
                    "symbol": r.symbol,
                    "date": r.date,
                    "price": r.price,
                    "provider": r.provider,
                }
                for r in rows
            ]
    except Exception as exc:
        logger.error("get_prices: error for %s: %s", symbol, exc)
        return []


def set_api_key(engine, provider: str, plaintext_key: str) -> bool:
    """
    @brief Store or update a provider API key in the api_keys table.

    The key is base64-encoded before storage. It is never stored in plain text.

    @param engine SQLAlchemy Engine instance.
    @param provider Provider identifier (e.g. 'alpha_vantage').
    @param plaintext_key The raw API key string.
    @return True on success, False on error.
    """
    encoded = _encode_key(plaintext_key)
    try:
        with get_session(engine) as session:
            existing = session.execute(
                select(ApiKey).where(ApiKey.provider == provider)
            ).scalar_one_or_none()

            now = datetime.utcnow()
            if existing:
                existing.encrypted_key = encoded
                existing.updated_at = now
                logger.info("set_api_key: updated key for provider '%s'", provider)
            else:
                record = ApiKey(
                    provider=provider,
                    encrypted_key=encoded,
                    created_at=now,
                    updated_at=now,
                )
                session.add(record)
                logger.info("set_api_key: stored new key for provider '%s'", provider)
            return True
    except Exception as exc:
        logger.error("set_api_key: error for provider '%s': %s", provider, exc)
        return False


def get_api_key(engine, provider: str) -> Optional[str]:
    """
    @brief Retrieve the plaintext API key for a given provider.
    @param engine SQLAlchemy Engine instance.
    @param provider Provider identifier string.
    @return Decoded plaintext key, or None if not found.
    """
    try:
        with get_session(engine) as session:
            row = session.execute(
                select(ApiKey).where(ApiKey.provider == provider)
            ).scalar_one_or_none()
            if row is None:
                logger.debug("get_api_key: no key found for provider '%s'", provider)
                return None
            return _decode_key(row.encrypted_key)
    except Exception as exc:
        logger.error("get_api_key: error for provider '%s': %s", provider, exc)
        return None


def update_sync_state(
    engine,
    last_sync_at: Optional[datetime] = None,
    conflict_status: str = "none",
    local_hash: Optional[str] = None,
    remote_hash: Optional[str] = None,
) -> bool:
    """
    @brief Update the sync state record (upsert — always exactly one row).
    @param engine SQLAlchemy Engine instance.
    @param last_sync_at Timestamp of the last successful sync.
    @param conflict_status Status string: 'none' | 'conflict' | 'resolved'.
    @param local_hash SHA-256 hash of local file.
    @param remote_hash SHA-256 hash of remote file.
    @return True on success, False on error.
    """
    try:
        with get_session(engine) as session:
            existing = session.execute(select(SyncState)).scalar_one_or_none()
            if existing:
                if last_sync_at is not None:
                    existing.last_sync_at = last_sync_at
                existing.conflict_status = conflict_status
                if local_hash is not None:
                    existing.local_hash = local_hash
                if remote_hash is not None:
                    existing.remote_hash = remote_hash
            else:
                record = SyncState(
                    last_sync_at=last_sync_at,
                    conflict_status=conflict_status,
                    local_hash=local_hash,
                    remote_hash=remote_hash,
                )
                session.add(record)
            logger.debug("update_sync_state: status='%s'", conflict_status)
            return True
    except Exception as exc:
        logger.error("update_sync_state: error: %s", exc)
        return False


def get_sync_state(engine) -> Optional[dict]:
    """
    @brief Retrieve the current sync state record.
    @param engine SQLAlchemy Engine instance.
    @return Dict with sync state fields, or None if no record exists.
    """
    try:
        with get_session(engine) as session:
            row = session.execute(select(SyncState)).scalar_one_or_none()
            if row is None:
                return None
            return {
                "last_sync_at": row.last_sync_at,
                "conflict_status": row.conflict_status,
                "local_hash": row.local_hash,
                "remote_hash": row.remote_hash,
            }
    except Exception as exc:
        logger.error("get_sync_state: error: %s", exc)
        return None
