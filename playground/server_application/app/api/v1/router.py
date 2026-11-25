from fastapi import APIRouter

from app.api.v1.routes import health
from app.institution_dashboard.routes import router as institution_dashboard_router

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(institution_dashboard_router)
