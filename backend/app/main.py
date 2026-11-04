"""FastAPI application factory.

Run locally with: uvicorn app.main:app --reload
Interactive API docs: /api/docs
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="DocIntel API",
        version=__version__,
        description="Document intelligence: upload, extract, validate and search invoices.",
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    # Only the frontend origin may call the API from a browser (CLAUDE.md, security rule 7).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        max_age=600,
    )
    # Refuse an oversized upload before reading it: a full batch at the size limit,
    # plus room for the multipart framing.
    max_body = (settings.max_file_mb * settings.max_files_per_batch + 1) * 1024 * 1024

    @app.middleware("http")
    async def limit_body_size(request: Request, call_next):  # type: ignore[no-untyped-def]
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > max_body:
            return JSONResponse({"detail": "the upload is too large"}, status_code=413)
        return await call_next(request)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
        """Responses are data, never pages to frame or sniff, and never cached (D63)."""
        response = await call_next(request)
        headers = response.headers
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Referrer-Policy", "no-referrer")
        headers.setdefault("Cache-Control", "no-store")
        if not request.url.path.startswith("/api/docs"):  # Swagger UI loads its own scripts
            headers.setdefault(
                "Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'"
            )
        if settings.is_production:
            headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

    app.include_router(api_router)
    return app


app = create_app()
