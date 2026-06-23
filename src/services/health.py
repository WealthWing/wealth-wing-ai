from __future__ import annotations

from typing import Any, Dict
from urllib import response

import httpx

from src.config import Settings


ProviderStatus = Dict[str, str]


async def build_health_report(settings: Settings) -> Dict[str, Any]:
    providers = {
        "together": await _check_together(settings),
        "wealth-wing-data": await _check_wealth_wing_data(settings),
    }
    overall_status = (
        "healthy"
        if all(provider["status"] == "healthy" for provider in providers.values())
        else "unhealthy"
    )

    return {
        "status": overall_status,
        "providers": providers,
    }


async def _check_together(settings: Settings) -> ProviderStatus:
    api_key = settings.together_api_key.get_secret_value()

    if api_key:
        return {"status": "healthy"}

    return {
        "status": "unhealthy",
        "reason": "not_configured",
    }


async def _check_wealth_wing_data(settings: Settings) -> ProviderStatus:
    health_url = settings.wealth_wing_data_health_url

    if not health_url:
        return {
            "status": "unhealthy",
            "reason": "not_configured",
        }

    is_healthy = await _ping_health_url(health_url)

    if is_healthy:
        return {"status": "healthy"}

    return {
        "status": "unhealthy",
        "reason": "health_check_failed",
    }


async def _ping_health_url(url: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(
                url,
                headers={"User-Agent": "wealth-wing-ai-health"},
            )
    
            return response.status_code == 200 
    except (httpx.HTTPError, ValueError):
        return False
