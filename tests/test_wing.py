import asyncio
import json
from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from main import create_app
from src.agents.wing.agent import WingAgent, _serialize_for_json
from src.agents.wing.configuration import WingAgentConfiguration
from src.agents.wing.nodes import WingAgentNodes
from src.agents.wing.profiles import get_profile
from src.agents.wing.prompts import get_system_prompt
from src.agents.wing.state import ResolvedFilters, StandardParams
from src.config import Settings
from src.routers import wing
from src.schemas.wing import WingAgentRequest


def make_settings(**overrides):
    settings_values = {
        "ALLOWED_HOSTS": "testserver",
        "COGNITO_JWKS_URL": "",
        "COGNITO_USER_POOL_ID": "",
        "AWS_REGION": "",
        "COGNITO_ISSUER": "",
        "COGNITO_CLIENT_ID": "",
        "TOGETHER_API_KEY": "test-key",
        "WEALTH_WING_DATA_HEALTH_URL": None,
    }
    settings_values.update(overrides)
    return Settings(**settings_values)


def expected_prompt(profile, additional_prompt=None):
    configuration = WingAgentConfiguration.from_settings(make_settings())
    prompt_parts = [
        get_system_prompt(configuration).strip(),
        get_profile(profile)["instructions"].strip(),
    ]

    if additional_prompt:
        prompt_parts.append(additional_prompt.strip())

    return "\n\n".join(prompt_parts)


def patch_agent_graph(monkeypatch):
    captured = {}

    class FakeGraph:
        async def ainvoke(self, state, context, config):
            captured["state"] = state
            captured["context"] = context
            captured["config"] = config
            return state

    class FakeBoundLLM:
        pass

    class FakeLLM:
        def bind_tools(self, tools):
            captured["bound_tools"] = [tool.name for tool in tools]
            return FakeBoundLLM()

    def fake_build_graph(**kwargs):
        captured["tools"] = [tool.name for tool in kwargs["tools"]]
        captured["tools_by_name"] = sorted(kwargs["tools_by_name"])
        captured["llm_type"] = type(kwargs["llm"]).__name__
        captured["llm_with_tools_type"] = type(kwargs["llm_with_tools"]).__name__
        return FakeGraph()

    monkeypatch.setattr(WingAgent, "_build_llm", lambda self: FakeLLM())
    monkeypatch.setattr("src.agents.wing.agent.build_graph", fake_build_graph)
    return captured


def test_wing_agent_route_is_protected_by_default():
    client = TestClient(create_app(make_settings()))

    response = client.post("/agents/wing/invoke", json={"message": "hello"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"


def test_wing_agent_route_invokes_with_runtime_context(monkeypatch):
    captured = patch_agent_graph(monkeypatch)
    app = FastAPI()
    app.state.settings = make_settings()
    app.include_router(wing.router, prefix="/agents/wing")
    client = TestClient(app)

    response = client.post(
        "/agents/wing/invoke",
        json={
            "message": "hello",
            "additional_prompt": "Prefer concise answers.",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "messages": [{"role": "human", "content": "hello"}],
        "additional_prompt": "Prefer concise answers.",
        "profile": "imports",
        "resolved_system_prompt": expected_prompt(
            "imports",
            "Prefer concise answers.",
        ),
        "enabled_tools": [],
        "metadata": {},
    }
    assert set(captured["state"]) == {"current_turn_id", "messages", "current_turn"}
    assert captured["state"]["current_turn"]["user_input"] == "hello"
    assert captured["context"]["agent_profile"] == "imports"
    assert captured["context"]["additional_prompt"] == "Prefer concise answers."
    assert captured["llm_type"] == "FakeLLM"
    assert captured["llm_with_tools_type"] == "FakeLLM"


def test_wing_agent_route_uses_explicit_insights_profile(monkeypatch):
    captured = patch_agent_graph(monkeypatch)
    app = FastAPI()
    app.state.settings = make_settings()
    app.include_router(wing.router, prefix="/agents/wing")
    client = TestClient(app)

    response = client.post(
        "/agents/wing/invoke",
        json={
            "message": "hello",
            "profile": "insights",
        },
    )

    tool_names = [tool.name for tool in get_profile("insights")["tools"]]
    assert response.status_code == 200
    assert response.json() == {
        "messages": [{"role": "human", "content": "hello"}],
        "additional_prompt": None,
        "profile": "insights",
        "resolved_system_prompt": expected_prompt("insights"),
        "enabled_tools": tool_names,
        "metadata": {},
    }
    assert captured["tools"] == tool_names
    assert captured["bound_tools"] == tool_names
    assert captured["llm_type"] == "FakeLLM"
    assert captured["llm_with_tools_type"] == "FakeBoundLLM"


def test_wing_agent_route_hides_intermediate_tool_call_messages(monkeypatch):
    class FakeGraph:
        async def ainvoke(self, state, context, config):
            return {
                "messages": [
                    HumanMessage(content="Can you explain my spending by category?"),
                    AIMessage(
                        content="I'm sorry, I don't have enough information.",
                        tool_calls=[
                            {
                                "name": "get_transactions_by_category",
                                "args": {},
                                "id": "call-1",
                            }
                        ],
                    ),
                    ToolMessage(
                        content="[transactions]",
                        tool_call_id="call-1",
                    ),
                    AIMessage(content="finalHere is your category breakdown."),
                ],
                "current_turn": state["current_turn"],
            }

    class FakeLLM:
        def bind_tools(self, tools):
            return self

    monkeypatch.setattr(WingAgent, "_build_llm", lambda self: FakeLLM())
    monkeypatch.setattr(
        "src.agents.wing.agent.build_graph",
        lambda **kwargs: FakeGraph(),
    )

    app = FastAPI()
    app.state.settings = make_settings()
    app.include_router(wing.router, prefix="/agents/wing")
    client = TestClient(app)

    response = client.post(
        "/agents/wing/invoke",
        json={
            "message": "Can you explain my spending by category?",
            "profile": "insights",
        },
    )

    assert response.status_code == 200
    assert response.json()["messages"] == [
        {
            "role": "human",
            "content": "Can you explain my spending by category?",
        },
        {
            "role": "ai",
            "content": "Here is your category breakdown.",
        },
    ]


def test_wing_agent_builds_initial_state_without_runtime_fields(monkeypatch):
    patch_agent_graph(monkeypatch)
    agent = WingAgent(settings=make_settings())

    state = agent._build_initial_state(
        WingAgentRequest(
            message="hello",
            additional_prompt="Prefer concise answers.",
            agent_profile="insights",
        )
    )

    assert set(state) == {"current_turn_id", "messages", "current_turn"}
    assert state["current_turn"]["user_input"] == "hello"
    assert state["current_turn"]["turn_id"]
    assert isinstance(state["messages"][0], HumanMessage)


def test_wing_agent_builds_runtime_context(monkeypatch):
    patch_agent_graph(monkeypatch)
    agent = WingAgent(settings=make_settings())

    context = agent._build_runtime_context(
        WingAgentRequest(
            message="hello",
            additional_prompt="Prefer concise answers.",
            agent_profile="insights",
        )
    )

    assert context["agent_profile"] == "insights"
    assert context["additional_prompt"] == "Prefer concise answers."
    assert context["resolved_system_prompt"] == expected_prompt(
        "insights",
        "Prefer concise answers.",
    )
    assert context["enabled_tools"] == tuple(
        tool.name for tool in get_profile("insights")["tools"]
    )


def test_wing_agent_debug_output_serializes_current_turn_models():
    current_turn = {
        "filters": ResolvedFilters(
            params=StandardParams(from_date=datetime(2026, 6, 1, 0, 0, 0)),
            date_source="explicit",
        )
    }

    serialized = _serialize_for_json(current_turn)

    assert json.loads(json.dumps(serialized)) == {
        "filters": {
            "params": {
                "page": 1,
                "page_size": 20,
                "sort_by": None,
                "sort_order": "desc",
                "search": None,
                "filter_by": [],
                "from_date": "2026-06-01T00:00:00",
                "to_date": None,
            },
            "date_source": "explicit",
        }
    }


def test_wing_agent_nodes_read_profile_and_prompt_from_runtime_context():
    class FakeRuntime:
        context = {
            "agent_profile": "insights",
            "resolved_system_prompt": "system from runtime",
        }

    class FakeLLM:
        def __init__(self):
            self.messages = []

        def invoke(self, messages: list[BaseMessage]) -> BaseMessage:
            self.messages = messages
            return AIMessage(content="ok")

    settings = make_settings()
    llm = FakeLLM()
    nodes = WingAgentNodes(
        settings=settings,
        configuration=WingAgentConfiguration.from_settings(settings),
        tools_by_name={},
        llm=llm,
        llm_with_tools=llm,
    )
    state = {
        "messages": [HumanMessage(content="hello")],
        "current_turn": {"turn_id": "turn-1", "user_input": "hello"},
        "agent_profile": "imports",
        "resolved_system_prompt": "state prompt should be ignored",
    }

    assert nodes.load_profile(state, FakeRuntime()) == {}
    response = asyncio.run(nodes._call_llm(state, FakeRuntime()))

    assert response == {"messages": [AIMessage(content="ok")]}
    assert isinstance(llm.messages[0], SystemMessage)
    assert llm.messages[0].content == "system from runtime"
