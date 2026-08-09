import asyncio
from typing import cast

from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver

from src.agents.wing.configuration import WingAgentConfiguration
from src.agents.wing.graph import build_graph
from src.agents.wing.state import FinalAnswer

from tests.test_wing import make_settings


def as_chat_model(model: object) -> ChatOpenAI:
    return cast(ChatOpenAI, model)


class FakeStructuredLLM:
    def __init__(self, response):
        self.response = response

    async def ainvoke(self, messages):
        return self.response


class FakeBaseLLM:
    def with_structured_output(self, schema):
        if schema is FinalAnswer:
            return FakeStructuredLLM(FinalAnswer(answer="Summary complete."))
        raise AssertionError(f"Unexpected schema: {schema}")


def test_graph_routes_tool_calls_directly_to_tools():
    @tool
    async def summary_tool() -> dict:
        """Return a deterministic summary."""
        return {
            "result_type": "transaction_summary",
            "data": {"net_activity": 100},
            "metadata": {},
        }

    settings = make_settings()
    graph = build_graph(
        configuration=WingAgentConfiguration.from_settings(settings),
        tools=(summary_tool,),
        llm=as_chat_model(FakeBaseLLM()),
        llm_with_tools=as_chat_model(object()),
        settings=settings,
        tools_by_name={"summary_tool": summary_tool},
    )

    assert set(graph.nodes) == {
        "__start__",
        "llm",
        "tools",
        "collect_results",
        "final_answer",
    }
    edges = {
        (edge.source, edge.target)
        for edge in graph.get_graph().edges
    }
    assert ("llm", "tools") in edges
    assert ("tools", "collect_results") in edges


def test_build_graph_compiles_for_profile_without_tools():
    settings = make_settings()
    checkpointer = InMemorySaver()

    @tool
    async def repeated_summary() -> dict:
        """Return a deterministic summary."""
        return {
            "result_type": "transaction_summary",
            "data": {"net_activity": 100},
            "metadata": {},
        }

    configuration = WingAgentConfiguration.from_settings(settings)
    tool_llm = FakeBaseLLM()

    graph = build_graph(
        configuration=configuration,
        tools=(repeated_summary,),
        llm=as_chat_model(FakeBaseLLM()),
        llm_with_tools=as_chat_model(tool_llm),
        settings=settings,
        tools_by_name={"repeated_summary": repeated_summary},
    )

    assert graph is not None
    assert graph.checkpointer is checkpointer


def test_graph_stops_repeated_successful_tool_call_before_recursion_limit():
    tool_execution_count = 0

    @tool
    async def repeated_summary(text: str) -> dict:
        """Return a deterministic transaction summary."""
        nonlocal tool_execution_count
        tool_execution_count += 1
        return {
            "result_type": "transaction_summary",
            "data": {"net_activity": 100},
            "metadata": {},
        }

    class RepeatingToolLLM:
        call_count = 0

        async def ainvoke(self, messages):
            self.call_count += 1
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": repeated_summary.name,
                        "args": {"text": f"summary attempt {self.call_count}"},
                        "id": f"call-{self.call_count}",
                    }
                ],
            )

    settings = make_settings()
    configuration = WingAgentConfiguration.from_settings(settings)
    tool_llm = RepeatingToolLLM()
    graph = build_graph(
        configuration=configuration,
        tools=(repeated_summary,),
        llm=as_chat_model(FakeBaseLLM()),
        llm_with_tools=as_chat_model(tool_llm),
        settings=settings,
        tools_by_name={"repeated_summary": repeated_summary},
    )

    result = asyncio.run(
        graph.ainvoke(
            {
                "messages": [],
                "current_turn": {
                    "turn_id": "turn-1",
                    "user_input": "Summarize last three months please.",
                },
            },
            context={"agent_profile": "insights"},
            config={"recursion_limit": configuration.recursion_limit},
        )
    )

    assert result["current_turn"]["final_answer"] == "Summary complete."
    assert result["current_turn"]["tool_round_count"] == 1
    assert len(result["current_turn"]["tool_results"]) == 1
    assert tool_llm.call_count == 2
    assert tool_execution_count == 1


def test_graph_finalizes_at_configured_tool_round_limit():
    tool_execution_count = 0

    @tool
    async def bounded_summary(text: str, period: int) -> dict:
        """Return a deterministic transaction summary for one period."""
        nonlocal tool_execution_count
        tool_execution_count += 1
        return {
            "result_type": "transaction_summary",
            "data": {"period": period, "net_activity": period * 100},
            "metadata": {},
        }

    class BoundedToolLLM:
        call_count = 0

        async def ainvoke(self, messages):
            self.call_count += 1
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": bounded_summary.name,
                        "args": {
                            "text": f"summary period {self.call_count}",
                            "period": self.call_count,
                        },
                        "id": f"call-{self.call_count}",
                    }
                ],
            )

    settings = make_settings()
    configuration = WingAgentConfiguration.from_settings(settings)
    tool_llm = BoundedToolLLM()
    graph = build_graph(
        configuration=configuration,
        tools=(bounded_summary,),
        llm=as_chat_model(FakeBaseLLM()),
        llm_with_tools=as_chat_model(tool_llm),
        settings=settings,
        tools_by_name={"bounded_summary": bounded_summary},
    )

    result = asyncio.run(
        graph.ainvoke(
            {
                "messages": [],
                "current_turn": {
                    "turn_id": "turn-1",
                    "user_input": "Summarize last three months please.",
                },
            },
            context={"agent_profile": "insights"},
            config={"recursion_limit": configuration.recursion_limit},
        )
    )

    assert result["current_turn"]["final_answer"] == "Summary complete."
    assert result["current_turn"]["tool_round_count"] == 3
    assert len(result["current_turn"]["tool_results"]) == 3
    assert tool_llm.call_count == 4
    assert tool_execution_count == 3
