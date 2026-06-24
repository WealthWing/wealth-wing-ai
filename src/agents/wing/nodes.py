from __future__ import annotations

from dataclasses import dataclass

from src.agents.wing.configuration import WingAgentConfiguration
from src.agents.wing.prompts import get_system_prompt
from src.agents.wing.profiles import DEFAULT_PROFILE, get_profile
from src.agents.wing.state import WingAgentState
from src.agents.wing.tools import get_tools
from src.config import Settings


@dataclass(frozen=True)
class WingAgentNodes:
    settings: Settings
    configuration: WingAgentConfiguration

    def prepare_context(self, state: WingAgentState) -> WingAgentState:
        profile_id = state.get("profile") or DEFAULT_PROFILE
        profile = get_profile(profile_id)
        tools = get_tools(profile_id)
        resolved_system_prompt = "\n\n".join(
            (
                get_system_prompt(self.configuration).strip(),
                profile["instructions"].strip(),
            )
        )

        return {
            "profile": profile_id,
            "resolved_system_prompt": resolved_system_prompt,
            "enabled_tools": tuple(tool.name for tool in tools),
            "metadata": dict(self.configuration.metadata),
        }
