"""FastAPI application factory for the research web boundary."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, Mapping

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ..providers.postgres_repository import PostgresAnalysisRepository
from ..runtime_config import load_settings
from ..service import DatabaseUnavailableError, RunConfigurationError
from .errors import ApiError
from .jobs import AnalysisJobService
from .routes import create_router
from .schemas import ErrorDetail, ErrorEnvelope


def _error_response(
    status_code: int,
    code: str,
    message: str,
    *,
    retryable: bool = False,
) -> JSONResponse:
    envelope = ErrorEnvelope(
        error=ErrorDetail(code=code, message=message, retryable=retryable)
    )
    return JSONResponse(status_code=status_code, content=envelope.model_dump())


def _max_workers(settings: Mapping[str, str]) -> int:
    raw_value = settings.get("DLP_API_MAX_WORKERS", "1").strip() or "1"
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RunConfigurationError(
            "DLP_API_MAX_WORKERS must be an integer between 1 and 8"
        ) from exc
    if not 1 <= value <= 8:
        raise RunConfigurationError(
            "DLP_API_MAX_WORKERS must be between 1 and 8"
        )
    return value


def create_app(
    repository: Any = None,
    job_service: Any = None,
    settings: Mapping[str, str] | None = None,
) -> FastAPI:
    resolved_settings = dict(load_settings() if settings is None else settings)
    if repository is None:
        dsn = resolved_settings.get("DATABASE_URL", "").strip()
        if not dsn:
            raise RunConfigurationError("DATABASE_URL is required for the API")
        repository = PostgresAnalysisRepository(dsn)
    if job_service is None:
        job_service = AnalysisJobService(
            repository,
            resolved_settings,
            max_workers=_max_workers(resolved_settings),
        )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        job_service.recover()
        try:
            yield
        finally:
            job_service.shutdown()

    app = FastAPI(title="Diagram LangGraph Pipeline API", lifespan=lifespan)
    origins = [
        item.strip()
        for item in resolved_settings.get(
            "DLP_CORS_ORIGINS",
            "http://127.0.0.1:8501,http://localhost:8501",
        ).split(",")
        if item.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.include_router(create_router(repository, job_service, resolved_settings))

    @app.exception_handler(ApiError)
    async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
        return _error_response(
            exc.status_code,
            exc.code,
            exc.message,
            retryable=exc.retryable,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request, _exc: RequestValidationError
    ) -> JSONResponse:
        return _error_response(422, "VALIDATION_ERROR", "Invalid request")

    @app.exception_handler(RunConfigurationError)
    async def configuration_error_handler(
        _request: Request, _exc: RunConfigurationError
    ) -> JSONResponse:
        return _error_response(422, "RUN_CONFIGURATION_ERROR", "Invalid run configuration")

    @app.exception_handler(DatabaseUnavailableError)
    async def database_error_handler(
        _request: Request, _exc: DatabaseUnavailableError
    ) -> JSONResponse:
        return _error_response(
            503,
            "STORAGE_UNAVAILABLE",
            "Storage service unavailable",
            retryable=True,
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(
        _request: Request, _exc: Exception
    ) -> JSONResponse:
        return _error_response(500, "INTERNAL_ERROR", "Internal server error")

    return app
