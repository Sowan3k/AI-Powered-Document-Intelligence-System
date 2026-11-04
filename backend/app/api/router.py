"""The /api router."""

from fastapi import APIRouter

from app.api.routes import (
    activity,
    auth,
    documents,
    export,
    health,
    invoices,
    jobs,
    reconcile,
    search,
)

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(documents.router)
api_router.include_router(jobs.router)
api_router.include_router(invoices.router)
api_router.include_router(search.router)
api_router.include_router(reconcile.router)
api_router.include_router(activity.router)
api_router.include_router(export.router)
