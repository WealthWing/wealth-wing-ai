from __future__ import annotations

from typing import Any

from fastapi import Request
from langgraph.checkpoint.base import BaseCheckpointSaver

from src.config import Settings
from src.providers.ww_data_client import WWDataClient


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_ww_data_client(request: Request) -> WWDataClient | None:
    return getattr(request.app.state, "ww_data_client", None)


def get_wing_checkpointer(request: Request) -> BaseCheckpointSaver[Any]:
    return request.app.state.wing_checkpointer
