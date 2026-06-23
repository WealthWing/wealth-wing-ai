from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from src.agents.wing.configuration import WingAgentConfiguration
from src.agents.wing.nodes import WingAgentNodes
from src.agents.wing.state import WingAgentState
from src.config import Settings


def build_graph(
    settings: Settings,
    configuration: WingAgentConfiguration,
) -> Any:
    nodes = WingAgentNodes(settings=settings, configuration=configuration)

    graph = StateGraph(WingAgentState)
    graph.add_node("prepare_context", nodes.prepare_context)
    graph.add_edge(START, "prepare_context")
    graph.add_edge("prepare_context", END)

    return graph.compile()
