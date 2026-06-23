import logging

from fastapi import APIRouter, Request, Response

from src.config import get_settings
from src.services.health import build_health_report

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("")
async def health(request: Request, response: Response):
    logger.info("Health endpoint called")
    settings = getattr(request.app.state, "settings", None) or get_settings()
    report = await build_health_report(settings)

    if report["status"] != "healthy":
        response.status_code = 503

    return report


@router.get("/ping")
async def ping():
    logger.info("Ping endpoint called")
    return {"message": "healthy"}
