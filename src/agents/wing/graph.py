from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langchain_core.tools import ToolException
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from src.agents.wing.configuration import WingAgentConfiguration
from src.agents.wing.nodes import WingAgentNodes
from src.agents.wing.state import WingGraphState, WingRuntimeContext
from src.config import Settings


def build_graph(
    settings: Settings,
    configuration: WingAgentConfiguration,
    tools_by_name: dict[str, Any],
    tools: tuple[Any, ...],
    llm: ChatOpenAI,
    llm_with_tools: ChatOpenAI,
    checkpointer: Any = None,
    llm_factory: Callable[[float | None], ChatOpenAI] | None = None,
) -> Any:
    nodes = WingAgentNodes(
        settings=settings,
        configuration=configuration,
        tools_by_name=tools_by_name,
        llm=llm,
        llm_with_tools=llm_with_tools,
        llm_factory=llm_factory,
    )

    graph = StateGraph(WingGraphState, context_schema=WingRuntimeContext)
    graph.add_node("load_profile", nodes.load_profile)
    graph.add_node("llm", nodes._call_llm)
    graph.add_edge(START, "load_profile")
    graph.add_edge("load_profile", "llm")

    if tools:
        graph.add_node(
            "tools",
            ToolNode(tools, handle_tool_errors=_safe_tool_error),
        )
        graph.add_node("resolve_filters", nodes.resolve_filters)
        graph.add_node("collect_results", nodes.collect_results)
        graph.add_node("final_answer", nodes.final_response)
        
        graph.add_conditional_edges(
            "llm",
            nodes.route_after_llm,
            {
                "resolve_filters": "resolve_filters",
                "final_answer": "final_answer",
            },
        )
        graph.add_edge("resolve_filters", "tools")
        graph.add_edge("tools", "collect_results")
        graph.add_conditional_edges(
            "collect_results",
            nodes.route_after_tool_results,
            {"llm": "llm", "final_answer": "final_answer"},
        )
        graph.add_edge("final_answer", END)
    else:
        # No-tool profiles still record their final answer in CurrentTurn so
        # all endpoint responses have the same canonical source.
        graph.add_node("record_direct_response", nodes.record_direct_response)
        graph.add_edge("llm", "record_direct_response")
        graph.add_edge("record_direct_response", END)

    return graph.compile(checkpointer=checkpointer)


def _safe_tool_error(error: Exception) -> str:
    if isinstance(error, ToolException):
        return str(error)
    return "The requested financial data could not be retrieved."
