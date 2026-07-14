import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from src.config import Settings
from src.dependencies import get_app_settings
from src.services.health import build_health_report

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("")
async def health(
    response: Response,
    settings: Annotated[Settings, Depends(get_app_settings)],
):
    logger.info("Health endpoint called")
    report = await build_health_report(settings)

    if report["status"] != "healthy":
        response.status_code = 503

    return report


@router.get("/ping")
async def ping():
    logger.info("Ping endpoint called")
    return {"message": "healthy"}
