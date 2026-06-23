from __future__ import annotations

from src.agents.wing.configuration import WingAgentConfiguration
from src.agents.wing.graph import build_graph
from src.agents.wing.state import WingAgentState
from src.config import Settings


class WingAgent:
    def __init__(
        self,
        settings: Settings,
        configuration: WingAgentConfiguration | None = None,
    ) -> None:
        self.settings = settings
        self.configuration = configuration or WingAgentConfiguration.from_settings(
            settings
        )
        self.graph = build_graph(
            settings=self.settings,
            configuration=self.configuration,
        )

    def invoke(self, state: WingAgentState) -> WingAgentState:
        return self.graph.invoke(
            state,
            config={"recursion_limit": self.configuration.recursion_limit},
        )

    async def ainvoke(self, state: WingAgentState) -> WingAgentState:
        return await self.graph.ainvoke(
            state,
            config={"recursion_limit": self.configuration.recursion_limit},
        )
