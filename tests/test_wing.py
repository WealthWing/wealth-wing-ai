import asyncio
import json
from datetime import datetime
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.checkpoint.memory import InMemorySaver

from main import create_app
from src.agents.wing.agent import WingAgent, _serialize_for_json
from src.agents.wing.configuration import WingAgentConfiguration
from src.agents.wing.nodes import WingAgentNodes
from src.agents.wing.profiles import get_profile
from src.agents.wing.prompts import get_system_prompt
from src.agents.wing.state import ResolvedFilters, StandardParams
from src.config import Settings
from src.dependencies import get_wing_checkpointer
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
            return {
                **state,
                "current_turn": {
                    **state["current_turn"],
                    "final_answer": "Hello from Wing.",
                },
            }

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
        captured["checkpointer"] = kwargs["checkpointer"]
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
    checkpointer = InMemorySaver()
    app.dependency_overrides[get_wing_checkpointer] = lambda: checkpointer
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
    body = response.json()
    assert body["answer"] == "Hello from Wing."
    assert body["results"] == []
    assert body["applied_filters"] is None
    assert body["error"] is None
    assert body["turn_id"] == captured["state"]["current_turn"]["turn_id"]
    assert UUID(body["thread_id"])
    assert set(body) == {
        "thread_id",
        "turn_id",
        "answer",
        "results",
        "applied_filters",
        "error",
    }
    assert set(captured["state"]) == {"current_turn_id", "messages", "current_turn"}
    assert captured["state"]["current_turn"]["user_input"] == "hello"
    assert captured["context"]["agent_profile"] == "imports"
    assert captured["context"]["additional_prompt"] == "Prefer concise answers."
    assert captured["llm_type"] == "FakeLLM"
    assert captured["llm_with_tools_type"] == "FakeLLM"
    assert captured["checkpointer"] is checkpointer


def test_wing_agent_route_continues_requested_thread(monkeypatch):
    captured = patch_agent_graph(monkeypatch)
    app = FastAPI()
    app.state.settings = make_settings()
    checkpointer = InMemorySaver()
    app.state.wing_checkpointer = checkpointer

    @app.middleware("http")
    async def add_authenticated_user(request, call_next):
        request.state.user_uuid = "user-123"
        return await call_next(request)

    app.include_router(wing.router, prefix="/agents/wing")
    client = TestClient(app)
    thread_id = uuid4()

    response = client.post(
        "/agents/wing/invoke",
        json={"message": "hello again", "thread_id": str(thread_id)},
    )

    assert response.status_code == 200
    assert response.json()["thread_id"] == str(thread_id)
    assert captured["checkpointer"] is checkpointer
    assert captured["config"]["configurable"]["thread_id"] == (
        f"user-123:imports:{thread_id}"
    )


def test_wing_agent_route_uses_explicit_insights_profile(monkeypatch):
    captured = patch_agent_graph(monkeypatch)
    app = FastAPI()
    app.state.settings = make_settings()
    app.state.wing_checkpointer = InMemorySaver()
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
    body = response.json()
    assert body["answer"] == "Hello from Wing."
    assert body["results"] == []
    assert body["applied_filters"] is None
    assert body["error"] is None
    assert body["turn_id"] == captured["state"]["current_turn"]["turn_id"]
    assert captured["tools"] == tool_names
    assert captured["bound_tools"] == tool_names
    assert captured["llm_type"] == "FakeLLM"
    assert captured["llm_with_tools_type"] == "FakeBoundLLM"


def test_spending_by_category_tool_is_available_to_insights_only():
    insights_tools = {tool.name for tool in get_profile("insights")["tools"]}

    assert "get_spending_by_category" in insights_tools
    assert all(
        "get_spending_by_category"
        not in {tool.name for tool in get_profile(profile)["tools"]}
        for profile in ("imports", "planning")
    )


def test_wing_agent_route_returns_sanitized_current_turn_results(monkeypatch):
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
                "current_turn": {
                    **state["current_turn"],
                    "final_answer": "Here is your category breakdown.",
                    "tool_results": [
                        {
                            "result_id": "call-1",
                            "result_type": "transaction_list",
                            "source_tool": "get_transactions",
                            "metadata": {"upstream": "do not expose"},
                            "ui": "transactions_ui",
                            "data": {
                                "transactions": [
                                    {
                                        "id": "transaction-1",
                                        "title": "Coffee",
                                        "amount_cents": 500,
                                        "user_id": "private-user-id",
                                        "provider_payload": "private",
                                    }
                                ],
                                "page": 1,
                                "total_count": 1,
                                "provider_payload": "private",
                            },
                        }
                    ],
                },
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
    app.state.wing_checkpointer = InMemorySaver()
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
    body = response.json()
    assert body == {
        "thread_id": body["thread_id"],
        "turn_id": body["turn_id"],
        "answer": "Here is your category breakdown.",
        "results": [
            {
                "id": "call-1",
                "type": "transaction_list",
                "ui": "transactions_ui",
                "data": {
                    "transactions": [
                        {
                            "id": "transaction-1",
                            "title": "Coffee",
                            "amount_cents": 500,
                        }
                    ],
                    "page": 1,
                    "total_count": 1,
                },
            }
        ],
        "applied_filters": None,
        "error": None,
    }


def test_wing_agent_route_returns_sanitized_cash_flow_results(monkeypatch):
    class FakeGraph:
        async def ainvoke(self, state, context, config):
            return {
                "current_turn": {
                    **state["current_turn"],
                    "final_answer": "Your June cash flow was positive.",
                    "tool_results": [
                        {
                            "result_id": "call-1",
                            "result_type": "cash_flow_history",
                            "source_tool": "get_cash_flow_history",
                            "metadata": {"source": "do not expose"},
                            "ui": "cash_flow_history",
                            "data": {
                                "timezone": "America/New_York",
                                "from_date": "2026-06-01",
                                "to_date": "2026-06-30",
                                "granularity": "month",
                                "periods": [
                                    {
                                        "period_start": "2026-06-01T00:00:00-04:00",
                                        "period_end": "2026-06-30T23:59:59.999999-04:00",
                                        "income": 520000,
                                        "expense": -184500,
                                        "refunds": 2500,
                                        "net": 338000,
                                        "transaction_count": 73,
                                        "provider_payload": "private",
                                    }
                                ],
                                "provider_payload": "private",
                            },
                        }
                    ],
                }
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
    app.state.wing_checkpointer = InMemorySaver()
    app.include_router(wing.router, prefix="/agents/wing")
    client = TestClient(app)

    response = client.post(
        "/agents/wing/invoke",
        json={"message": "Show my June cash flow.", "profile": "insights"},
    )

    assert response.status_code == 200
    assert response.json()["results"] == [
        {
            "id": "call-1",
            "type": "cash_flow_history",
            "ui": "cash_flow_history",
            "data": {
                "timezone": "America/New_York",
                "from_date": "2026-06-01",
                "to_date": "2026-06-30",
                "granularity": "month",
                "periods": [
                    {
                        "period_start": "2026-06-01T00:00:00-04:00",
                        "period_end": "2026-06-30T23:59:59.999999-04:00",
                        "income": 520000,
                        "expense": -184500,
                        "refunds": 2500,
                        "net": 338000,
                        "transaction_count": 73,
                    }
                ],
            },
        }
    ]


def test_wing_agent_route_returns_allowlisted_spending_by_category_results(
    monkeypatch,
):
    class FakeGraph:
        async def ainvoke(self, state, context, config):
            return {
                "current_turn": {
                    **state["current_turn"],
                    "final_answer": "Groceries were your largest expense.",
                    "tool_results": [
                        {
                            "result_id": "call-1",
                            "result_type": "spending_by_category",
                            "source_tool": "get_spending_by_category",
                            "metadata": {"source": "do not expose"},
                            "ui": "spending_by_category",
                            "data": {
                                "categories": [
                                    {
                                        "category_id": "43581d15-1a1d-49ce-adc6-f0fe6184f18a",
                                        "category": "Groceries",
                                        "expense": -8423,
                                        "total_spent": -8423,
                                        "category_slug": "groceries",
                                        "category_name": "Groceries",
                                        "total_cents": -8423,
                                        "transaction_count": 1,
                                        "percent_of_total": 100,
                                        "provider_payload": "private",
                                    }
                                ],
                                "total_spent": -8423,
                                "provider_payload": "private",
                            },
                        }
                    ],
                }
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
    app.state.wing_checkpointer = InMemorySaver()
    app.include_router(wing.router, prefix="/agents/wing")
    client = TestClient(app)

    response = client.post(
        "/agents/wing/invoke",
        json={"message": "Show my spending by category.", "profile": "insights"},
    )

    assert response.status_code == 200
    assert response.json()["results"] == [
        {
            "id": "call-1",
            "type": "spending_by_category",
            "ui": "spending_by_category",
            "data": {
                "categories": [
                    {
                        "category_id": "43581d15-1a1d-49ce-adc6-f0fe6184f18a",
                        "category": "Groceries",
                        "expense": -8423,
                    }
                ]
            },
        }
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


def test_wing_agent_configures_in_memory_checkpoints_per_run(monkeypatch):
    captured = patch_agent_graph(monkeypatch)
    agent = WingAgent(settings=make_settings())

    asyncio.run(agent.ainvoke("hello"))

    assert isinstance(agent.checkpointer, InMemorySaver)
    assert captured["checkpointer"] is agent.checkpointer
    assert captured["config"]["configurable"]["thread_id"] == captured["context"][
        "agent_run_id"
    ]


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


def test_wing_agent_keeps_runtime_credentials_private(monkeypatch):
    captured = patch_agent_graph(monkeypatch)
    provider_client = object()
    agent = WingAgent(
        settings=make_settings(),
        ww_data_client=provider_client,
        access_token="secret-token",
    )

    asyncio.run(
        agent.ainvoke(
            WingAgentRequest(message="hello", agent_profile="insights")
        )
    )

    assert captured["context"]["ww_data_client"] is provider_client
    assert captured["context"]["access_token"] == "secret-token"
    assert "ww_data_client" not in agent.last_runtime_context
    assert "access_token" not in agent.last_runtime_context
    assert "secret-token" not in json.dumps(_serialize_for_json(agent.last_runtime_context))


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
