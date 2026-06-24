from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from src.config import Settings


@dataclass(frozen=True)
class WingAgentConfiguration:
    default_model: str
    temperature: float = 0.2
    max_tokens: int | None = None
    recursion_limit: int = 25
    timeout_seconds: float = 30.0
    system_prompt_name: str = "default"
    stream: bool = False
    debug: bool = False
    metadata: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def from_settings(cls, settings: Settings) -> "WingAgentConfiguration":
        return cls(
            default_model=settings.model,
            debug=settings.environment.lower() != "production",
        )
