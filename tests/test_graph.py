from langgraph.checkpoint.memory import InMemorySaver

from src.agents.wing.configuration import WingAgentConfiguration
from src.agents.wing.graph import build_graph

from tests.test_wing import make_settings


def test_build_graph_compiles_for_profile_without_tools():
    settings = make_settings()
    checkpointer = InMemorySaver()

    graph = build_graph(
        settings=settings,
        configuration=WingAgentConfiguration.from_settings(settings),
        tools_by_name={},
        tools=(),
        llm=object(),
        llm_with_tools=object(),
        checkpointer=checkpointer,
    )

    assert graph is not None
    assert graph.checkpointer is checkpointer
