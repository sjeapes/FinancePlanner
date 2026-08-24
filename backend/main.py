"""
@file main.py
@brief LifeLedger FastAPI application factory and entry point.

Creates and configures the FastAPI application with:
  - CORS middleware (Vite dev server on localhost:5173)
  - Request logging middleware (method, path, status, duration)
  - Global exception handler returning structured JSON
  - Startup event: initialise database, load config, load tax profiles,
    initialise market data providers
  - Shutdown event: cleanup resources
  - All API routers registered under the /api prefix

Usage:
  cd c:/Users/Test/Documents/Projects/FinancePlanner
  python -m uvicorn backend.main:app --reload --port 8000
"""

import logging
import logging.handlers
import os
import sys
import time
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


# ── Logging configuration ─────────────────────────────────────────────────────

def _configure_logging(
    log_level: str = "INFO",
    log_file: Optional[str] = None,
    log_to_console: bool = True,
    log_to_file: bool = True,
    project_root: str = ".",
) -> None:
    """
    @brief Configure root logging handlers for file and console output.
    @param log_level Logging level string (DEBUG|INFO|WARNING|ERROR).
    @param log_file Relative path to log file from project root.
    @param log_to_console Whether to also log to stderr.
    @param log_to_file Whether to log to the file.
    @param project_root Project root directory path.
    """
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    fmt = "%(levelname)-8s %(name)-30s %(message)s"
    formatter = logging.Formatter(fmt)

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Remove existing handlers to avoid duplicates on reload
    root_logger.handlers.clear()

    if log_to_console:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    if log_to_file and log_file:
        abs_log = os.path.join(project_root, log_file)
        try:
            os.makedirs(os.path.dirname(abs_log), exist_ok=True)
            file_handler = logging.handlers.RotatingFileHandler(
                abs_log,
                maxBytes=10 * 1024 * 1024,  # 10 MB
                backupCount=5,
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
        except Exception as exc:
            print(f"WARNING: could not open log file {abs_log}: {exc}", file=sys.stderr)


# ── App factory ───────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    """
    @brief Create, configure, and return the LifeLedger FastAPI application.

    Sets up CORS, middleware, exception handlers, startup/shutdown events,
    and registers all API routers. Shared application state is stored on
    app.state to avoid global variables.

    @return Configured FastAPI application instance.
    """
    app = FastAPI(
        title="LifeLedger API",
        version="2.0.0",
        description="Self-hosted personal finance and retirement planning platform.",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",  # Vite dev server
            "http://localhost:3000",  # Fallback
            "http://127.0.0.1:5173",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Request logging middleware ────────────────────────────────────────────
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        """
        @brief Log each incoming request with method, path, status, and duration.
        @param request Incoming FastAPI Request.
        @param call_next Next middleware/handler in the chain.
        @return HTTP Response.
        """
        start = time.monotonic()
        try:
            response = await call_next(request)
            duration_ms = (time.monotonic() - start) * 1000
            logger.info(
                "HTTP %s %s → %d (%.1fms)",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
            )
            return response
        except Exception as exc:
            duration_ms = (time.monotonic() - start) * 1000
            logger.error(
                "HTTP %s %s → ERROR (%.1fms): %s",
                request.method,
                request.url.path,
                duration_ms,
                exc,
            )
            raise

    # ── Global exception handler ──────────────────────────────────────────────
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """
        @brief Handle all unhandled exceptions and return structured JSON.
        @param request The request that caused the exception.
        @param exc The unhandled exception.
        @return JSONResponse with error and detail fields.
        """
        logger.error(
            "Unhandled exception on %s %s: %s",
            request.method,
            request.url.path,
            exc,
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": type(exc).__name__,
                "detail": str(exc),
            },
        )

    # ── Startup event ─────────────────────────────────────────────────────────
    @app.on_event("startup")
    async def startup() -> None:
        """
        @brief Application startup: load config, init DB, init market data providers.

        Stores all shared state on app.state. Failures are logged but do not
        prevent the server from starting, to allow partial operation.
        """
        # Determine project root (two levels up from this file: backend/main.py)
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        app.state.project_root = project_root

        # ── Load config ───────────────────────────────────────────────────────
        config_path = os.path.join(project_root, "config", "lifeledger_config.yaml")
        try:
            from backend.persistence.yaml_serialiser import load_app_config_from_file
            config = load_app_config_from_file(config_path)
            app.state.config = config

            # Configure logging from loaded config
            raw = config.raw
            app_cfg = raw.get("app", {})
            _configure_logging(
                log_level=app_cfg.get("log_level", "INFO"),
                log_file=app_cfg.get("log_file", "logs/lifeledger.log"),
                log_to_console=bool(app_cfg.get("log_to_console", True)),
                log_to_file=bool(app_cfg.get("log_to_file", True)),
                project_root=project_root,
            )
            logger.info("startup: loaded config from %s", config_path)
        except Exception as exc:
            logger.error("startup: failed to load config: %s", exc, exc_info=True)
            from backend.models.models import AppConfig
            app.state.config = AppConfig()

        # ── Load tax profiles ─────────────────────────────────────────────────
        tax_profiles_path = os.path.join(project_root, "config", "tax_profiles.yaml")
        try:
            from backend.persistence.yaml_serialiser import load_tax_profiles_from_file

            profiles_list = load_tax_profiles_from_file(tax_profiles_path)
            app.state.tax_profiles = {p.id: p for p in profiles_list}
            logger.info(
                "startup: loaded %d tax profiles: %s",
                len(app.state.tax_profiles),
                list(app.state.tax_profiles.keys()),
            )
        except Exception as exc:
            logger.error("startup: failed to load tax profiles: %s", exc, exc_info=True)
            app.state.tax_profiles = {}

        # ── Initialise SQLite database ────────────────────────────────────────
        db_path = os.path.join(project_root, "data", "lifeledger.db")
        try:
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            from backend.persistence.sqlite_cache import get_engine, init_db

            db_engine = get_engine(db_path)
            init_db(db_path)
            app.state.db_engine = db_engine
            app.state.db_path = db_path
            logger.info("startup: SQLite initialised at %s", db_path)
        except Exception as exc:
            logger.error("startup: failed to init SQLite: %s", exc, exc_info=True)
            app.state.db_engine = None
            app.state.db_path = db_path

        # ── Initialise market data providers ──────────────────────────────────
        try:
            from backend.market_data.cache import PriceCache
            from backend.market_data.price_sync import PriceSyncManager
            from backend.market_data.providers.alpha_vantage import AlphaVantageProvider
            from backend.market_data.providers.finnhub_provider import FinnhubProvider
            from backend.market_data.providers.open_figi import OpenFIGIProvider
            from backend.market_data.providers.yfinance_provider import YFinanceProvider
            from backend.market_data.scheduler import RefreshScheduler
            from backend.market_data.symbol_search import SymbolSearcher
            from backend.persistence.sqlite_cache import get_api_key

            def _make_key_fn(provider_name: str):
                """
                @brief Create a closure that retrieves an API key for a provider.
                @param provider_name Provider identifier string.
                @return Callable that returns the key or None.
                """
                def _fn() -> Optional[str]:
                    engine = app.state.db_engine
                    if engine is None:
                        return None
                    return get_api_key(engine, provider_name)
                return _fn

            price_cache = PriceCache(db_path)
            app.state.price_cache = price_cache

            providers = [
                YFinanceProvider(),
                AlphaVantageProvider(get_api_key_fn=_make_key_fn("alpha_vantage")),
                FinnhubProvider(get_api_key_fn=_make_key_fn("finnhub")),
            ]
            app.state.providers = providers

            isin_resolver = OpenFIGIProvider(
                get_api_key_fn=_make_key_fn("open_figi")
            )
            app.state.isin_resolver = isin_resolver

            price_sync = PriceSyncManager(
                cache=price_cache,
                providers=providers,
                isin_resolver=isin_resolver,
            )
            app.state.price_sync = price_sync

            symbol_searcher = SymbolSearcher(
                providers=providers,
                isin_resolver=isin_resolver,
            )
            app.state.symbol_searcher = symbol_searcher

            scheduler = RefreshScheduler()
            scheduler.mark_app_opened()
            app.state.refresh_scheduler = scheduler

            logger.info(
                "startup: market data providers initialised: %s",
                [p.provider_name for p in providers],
            )
        except Exception as exc:
            logger.error(
                "startup: failed to initialise market data providers: %s", exc, exc_info=True
            )
            app.state.price_sync = None
            app.state.symbol_searcher = None
            app.state.refresh_scheduler = None

        logger.info("LifeLedger API v2.0.0 startup complete")

    # ── Shutdown event ────────────────────────────────────────────────────────
    @app.on_event("shutdown")
    async def shutdown() -> None:
        """
        @brief Application shutdown: dispose database engine and log cleanly.
        """
        try:
            engine = getattr(app.state, "db_engine", None)
            if engine is not None:
                engine.dispose()
                logger.info("shutdown: database engine disposed")
        except Exception as exc:
            logger.error("shutdown: error during cleanup: %s", exc)
        logger.info("LifeLedger API shutdown complete")

    # ── Register routers ──────────────────────────────────────────────────────
    _register_routers(app)

    return app


def _register_routers(app: FastAPI) -> None:
    """
    @brief Register all API route modules with the FastAPI application.

    Registers all phase routers under the /api prefix:
      Phase 1–3: simulation, scenarios, accounts, tax, checkpoints, sync, market_data
      Phase 4:   retirement
      Phase 5:   planning
      Phase 6:   reports

    @param app FastAPI application instance.
    """
    try:
        from backend.api.routes import (
            accounts,
            checkpoints,
            market_data,
            scenarios,
            simulation,
            sync,
            tax,
        )

        # ── Phase 1–3 routers ─────────────────────────────────────────────────
        app.include_router(simulation.router,   prefix="/api", tags=["simulation"])
        app.include_router(scenarios.router,    prefix="/api", tags=["scenarios"])
        app.include_router(accounts.router,     prefix="/api", tags=["accounts"])
        app.include_router(tax.router,          prefix="/api", tags=["tax"])
        app.include_router(checkpoints.router,  prefix="/api", tags=["checkpoints"])
        app.include_router(sync.router,         prefix="/api", tags=["sync"])
        app.include_router(market_data.router,  prefix="/api", tags=["market-data"])

        # ── Phase 4: Retirement planning ─────────────────────────────────────
        try:
            from backend.api.routes import retirement
            app.include_router(retirement.router, prefix="/api", tags=["retirement"])
            logger.debug("_register_routers: retirement router registered")
        except ImportError as exc:
            logger.warning("retirement router not available: %s", exc)

        # ── Phase 5: Advanced planning ────────────────────────────────────────
        try:
            from backend.api.routes import planning
            app.include_router(planning.router, prefix="/api", tags=["planning"])
            logger.debug("_register_routers: planning router registered")
        except ImportError as exc:
            logger.warning("planning router not available: %s", exc)

        # ── Phase 6: Report export ────────────────────────────────────────────
        try:
            from backend.api.routes import reports
            app.include_router(reports.router, prefix="/api", tags=["reports"])
            logger.debug("_register_routers: reports router registered")
        except ImportError as exc:
            logger.warning("reports router not available: %s", exc)

        logger.debug("_register_routers: all routers registered")
    except Exception as exc:
        logger.error("_register_routers: failed to register routers: %s", exc, exc_info=True)
        raise


# ── Module-level app instance ─────────────────────────────────────────────────

# Configure basic logging immediately so any import-time warnings are visible
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)-8s %(name)-30s %(message)s",
    stream=sys.stderr,
)

app = create_app()
