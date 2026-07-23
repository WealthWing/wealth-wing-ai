import asyncio

from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

from src.agents.wing.configuration import WingAgentConfiguration
from src.agents.wing.graph import build_graph
from src.agents.wing.state import FinalAnswer, ResolvedFilters

from tests.test_wing import make_settings


class FakeStructuredLLM:
    def __init__(self, response):
        self.response = response

    async def ainvoke(self, messages):
        return self.response


class FakeBaseLLM:
    def with_structured_output(self, schema):
        if schema is ResolvedFilters:
            return FakeStructuredLLM(ResolvedFilters())
        if schema is FinalAnswer:
            return FakeStructuredLLM(FinalAnswer(answer="Summary complete."))
        raise AssertionError(f"Unexpected schema: {schema}")


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
        settings=settings,
        configuration=configuration,
        tools_by_name={repeated_summary.name: repeated_summary},
        tools=(repeated_summary,),
        llm=FakeBaseLLM(),
        llm_with_tools=tool_llm,
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
        settings=settings,
        configuration=configuration,
        tools_by_name={bounded_summary.name: bounded_summary},
        tools=(bounded_summary,),
        llm=FakeBaseLLM(),
        llm_with_tools=tool_llm,
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
