"""API v1 router configuration.

This module sets up the main API router and includes all sub-routers for
versioned endpoints.
"""

from fastapi import APIRouter

from app.api.v1.routes import masking_router

api_router = APIRouter()
api_router.include_router(masking_router)
