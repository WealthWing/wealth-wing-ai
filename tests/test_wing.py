from fastapi import FastAPI
from fastapi.testclient import TestClient

from main import create_app
from src.agents.wing.configuration import WingAgentConfiguration
from src.agents.wing.profiles import get_profile
from src.agents.wing.prompts import get_system_prompt
from src.config import Settings
from src.routers import wing


def make_settings(**overrides):
    settings_values = {
        "ALLOWED_HOSTS": "testserver",
        "COGNITO_JWKS_URL": "",
        "COGNITO_USER_POOL_ID": "",
        "AWS_REGION": "",
        "COGNITO_ISSUER": "",
        "COGNITO_CLIENT_ID": "",
        "TOGETHER_API_KEY": "",
        "WEALTH_WING_DATA_HEALTH_URL": None,
    }
    settings_values.update(overrides)
    return Settings(**settings_values)


def expected_prompt(profile):
    configuration = WingAgentConfiguration.from_settings(make_settings())

    return "\n\n".join(
        (
            get_system_prompt(configuration).strip(),
            get_profile(profile)["instructions"].strip(),
        )
    )


def test_wing_agent_route_is_protected_by_default():
    client = TestClient(create_app(make_settings()))

    response = client.post("/agents/wing/invoke", json={"message": "hello"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"


def test_wing_agent_route_invokes_initial_graph():
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
        "resolved_system_prompt": expected_prompt("imports"),
        "enabled_tools": [],
        "metadata": {},
    }


def test_wing_agent_route_uses_explicit_insights_profile():
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

    assert response.status_code == 200
    assert response.json() == {
        "messages": [{"role": "human", "content": "hello"}],
        "additional_prompt": None,
        "profile": "insights",
        "resolved_system_prompt": expected_prompt("insights"),
        "enabled_tools": ["echo_context"],
        "metadata": {},
    }
