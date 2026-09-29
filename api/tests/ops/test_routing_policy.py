import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import text

from api.config.settings import settings
from api.contracts.enums import LLMPurpose
from api.db.engine import engine
from api.llm import routing as llm_routing
from api.llm.policy_repository import (
    DEFAULT_PURPOSES,
    get_current_policy,
    write_new_policy,
)
from api.main import app


@pytest.fixture(autouse=True)
def _reset_live_policy():
    """The in-process cache ``route_for`` reads (S9.6) is global state."""
    llm_routing.clear_live_policy()
    yield
    llm_routing.clear_live_policy()


@pytest_asyncio.fixture(autouse=True)
async def _clean_routing_policy_table():
    """``routingpolicy`` is append-only by design (migration 0012) and not in
    the root conftest's truncate list -- clean up this file's own rows rather
    than editing shared test infra for one owned feature."""
    yield
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE routingpolicy RESTART IDENTITY CASCADE"))


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


@pytest.mark.asyncio
async def test_get_current_policy_is_none_before_any_write(session):
    assert await get_current_policy(session) is None


@pytest.mark.asyncio
async def test_write_new_policy_starts_at_version_one(session):
    row = await write_new_policy(session, {LLMPurpose.ANSWER.value: "claude-frontier"})

    assert row.version == 1
    assert row.purposes == {LLMPurpose.ANSWER.value: "claude-frontier"}


@pytest.mark.asyncio
async def test_write_new_policy_is_append_only_not_an_update(session):
    """Each PUT is a new row (F7.3's own audit-trail requirement) -- never a
    mutation of the previous one."""
    first = await write_new_policy(session, {LLMPurpose.ANSWER.value: "a"})
    second = await write_new_policy(session, {LLMPurpose.ANSWER.value: "b"})

    assert second.version == first.version + 1
    current = await get_current_policy(session)
    assert current.id == second.id
    assert current.purposes == {LLMPurpose.ANSWER.value: "b"}


@pytest.mark.asyncio
async def test_get_routing_policy_route_returns_synthesized_defaults_when_unset(
    client: AsyncClient,
):
    response = await client.get("/api/ops/routing-policy")

    assert response.status_code == 200
    body = response.json()
    assert body["version"] == 0
    assert body["purposes"] == DEFAULT_PURPOSES


@pytest.mark.asyncio
async def test_put_routing_policy_persists_and_flips_the_live_route_immediately(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    """The closing-argument requirement (F7.3): a PUT must be visible to the
    very next call in this same process, not just the next request's fresh
    read from Postgres. ``answer`` is frontier-eligible (S9.7) so this needs a
    usable key -- without one the very fallback this sprint built would (and
    should) route it local instead; see
    ``test_put_routing_policy_flips_to_frontier_fallback_without_a_key``."""
    monkeypatch.setattr(settings, "frontier_model", "claude-frontier")
    monkeypatch.setattr(settings, "frontier_api_key", SecretStr("test-key"))

    response = await client.put(
        "/api/ops/routing-policy",
        json={"version": 0, "purposes": {LLMPurpose.ANSWER.value: "claude-frontier"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["version"] == 1
    assert body["purposes"][LLMPurpose.ANSWER.value] == "claude-frontier"

    route = llm_routing.route_for(LLMPurpose.ANSWER)
    assert route.model == "claude-frontier"
    assert route.frontier is True


@pytest.mark.asyncio
async def test_put_routing_policy_flips_to_frontier_fallback_without_a_key(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    """The live switch still takes effect with no key provisioned (this
    environment's actual state, S9.7) -- it just resolves through the local
    fallback rather than raising."""
    monkeypatch.setattr(settings, "frontier_model", None)
    monkeypatch.setattr(settings, "frontier_api_key", None)

    response = await client.put(
        "/api/ops/routing-policy",
        json={"version": 0, "purposes": {LLMPurpose.ANSWER.value: "claude-frontier"}},
    )

    assert response.status_code == 200

    route = llm_routing.route_for(LLMPurpose.ANSWER)
    assert route.frontier is False
    assert route.model == settings.llm_model
    assert route.fallback_reason == "frontier not configured"


@pytest.mark.asyncio
async def test_put_routing_policy_ignores_a_client_supplied_version(
    client: AsyncClient,
):
    """The version is the audit trail's own sequence number -- never
    client-supplied (migration 0012: every PUT is a new row)."""
    response = await client.put(
        "/api/ops/routing-policy",
        json={"version": 999, "purposes": {LLMPurpose.ANSWER.value: "claude-frontier"}},
    )

    assert response.status_code == 200
    assert response.json()["version"] == 1


@pytest.mark.asyncio
async def test_put_routing_policy_rejects_an_unknown_purpose(client: AsyncClient):
    response = await client.put(
        "/api/ops/routing-policy",
        json={"version": 0, "purposes": {"not_a_real_purpose": "x"}},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_routing_policy_resyncs_a_fresh_process_from_postgres(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    """A GET after a PUT from a different process (a fresh API server
    restart, in reality) must still resolve to the persisted policy -- not
    the hardcoded local defaults -- once it reads the table."""
    monkeypatch.setattr(settings, "frontier_model", "claude-frontier")
    monkeypatch.setattr(settings, "frontier_api_key", SecretStr("test-key"))

    await client.put(
        "/api/ops/routing-policy",
        json={"version": 0, "purposes": {LLMPurpose.ANSWER.value: "claude-frontier"}},
    )
    llm_routing.clear_live_policy()
    assert llm_routing.get_live_policy() is None

    response = await client.get("/api/ops/routing-policy")

    assert response.status_code == 200
    assert llm_routing.get_live_policy() is not None
    route = llm_routing.route_for(LLMPurpose.ANSWER)
    assert route.model == "claude-frontier"
