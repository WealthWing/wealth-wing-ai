from __future__ import annotations

from dataclasses import dataclass

from src.agents.wing.configuration import WingAgentConfiguration
from src.agents.wing.profiles import PROFILES
from src.agents.wing.state import WingAgentState
from src.config import Settings


@dataclass(frozen=True)
class WingAgentNodes:
    settings: Settings
    configuration: WingAgentConfiguration

    def load_profile(self, state: WingAgentState) -> WingAgentState:
        """Load the agent profile based on the provided state."""
        profile = state.get("agent_profile")

        if profile is None:
            return {
                "validation_errors": [
                    *state.get("validation_errors", []),
                    "agent_profile is required",
                ],
            }

        agent_system_profile = PROFILES.get(profile)
        if agent_system_profile is None:
            return {
                "validation_errors": [
                    *state.get("validation_errors", []),
                    f"Invalid agent_profile: {profile}",
                ],
            }
        return {
            "agent_system_profile": agent_system_profile,
        }
