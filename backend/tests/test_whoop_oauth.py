"""HTTP-level tests for the WHOOP OAuth endpoints. The token-exchange + sync
services are stubbed so nothing hits WHOOP; we test the auth-gating and that the
callback trusts the signed `state` (and rejects a Strava-minted one)."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_state_token
from app.models.user import User
from app.services import whoop as whoop_svc


async def test_whoop_authorize_requires_auth(client: AsyncClient):
    resp = await client.get("/auth/whoop/authorize")
    assert resp.status_code in (401, 403)


async def test_whoop_authorize_url_has_state_and_offline_scope(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.get("/auth/whoop/authorize", headers=auth_headers)
    assert resp.status_code == 200
    url = resp.json()["authorization_url"]
    assert "api.prod.whoop.com/oauth/oauth2/auth" in url
    assert "state=" in url
    assert "offline" in url  # the offline scope (required for refresh tokens)


async def test_whoop_callback_forged_state_redirects_to_error(client: AsyncClient):
    resp = await client.get(
        "/auth/whoop/callback", params={"code": "abc", "state": "forged"}
    )
    assert resp.status_code == 303
    assert "provider=whoop" in resp.headers["location"]
    assert "status=error" in resp.headers["location"]


async def test_whoop_callback_rejects_strava_state(client: AsyncClient, user: User):
    """A state minted for Strava must not connect WHOOP (provider mismatch)."""
    state = create_state_token(user.id, "strava")
    resp = await client.get(
        "/auth/whoop/callback", params={"code": "abc", "state": state}
    )
    assert resp.status_code == 303
    assert "status=error" in resp.headers["location"]


async def test_whoop_callback_valid_state_connects(
    client: AsyncClient, user: User, monkeypatch
):
    async def fake_exchange(code, u, d):
        u.whoop_access_token = "encrypted"

    async def fake_sync(u, d):
        return 0

    monkeypatch.setattr(whoop_svc, "exchange_code", fake_exchange)
    monkeypatch.setattr(whoop_svc, "sync_recovery", fake_sync)

    state = create_state_token(user.id, "whoop")
    resp = await client.get(
        "/auth/whoop/callback", params={"code": "abc", "state": state}
    )
    assert resp.status_code == 303
    assert "provider=whoop" in resp.headers["location"]
    assert "status=connected" in resp.headers["location"]


async def test_connections_whoop_true_after_token_stored(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, user: User
):
    user.whoop_access_token = "encrypted-token"
    await db.commit()

    resp = await client.get("/auth/connections", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["whoop_connected"] is True
