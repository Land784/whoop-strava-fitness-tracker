"""HTTP-level tests for the Dexcom OAuth endpoints. The token-exchange + sync
services are stubbed so nothing hits Dexcom; we test the auth-gating and that the
callback trusts the signed `state` (and rejects a WHOOP-minted one)."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_state_token
from app.models.user import User
from app.services import dexcom as dexcom_svc


async def test_dexcom_authorize_requires_auth(client: AsyncClient):
    resp = await client.get("/auth/dexcom/authorize")
    assert resp.status_code in (401, 403)


async def test_dexcom_authorize_url_has_state_and_offline_scope(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.get("/auth/dexcom/authorize", headers=auth_headers)
    assert resp.status_code == 200
    url = resp.json()["authorization_url"]
    # Default config is sandbox, so the authorize host is the sandbox host.
    assert "sandbox-api.dexcom.com" in url
    assert "/v2/oauth2/login" in url
    assert "state=" in url
    assert "offline_access" in url  # required for a refresh token


async def test_dexcom_callback_forged_state_redirects_to_error(client: AsyncClient):
    resp = await client.get(
        "/auth/dexcom/callback", params={"code": "abc", "state": "forged"}
    )
    assert resp.status_code == 303
    assert "provider=dexcom" in resp.headers["location"]
    assert "status=error" in resp.headers["location"]


async def test_dexcom_callback_rejects_whoop_state(client: AsyncClient, user: User):
    """A state minted for WHOOP must not connect Dexcom (provider mismatch)."""
    state = create_state_token(user.id, "whoop")
    resp = await client.get(
        "/auth/dexcom/callback", params={"code": "abc", "state": state}
    )
    assert resp.status_code == 303
    assert "status=error" in resp.headers["location"]


async def test_dexcom_callback_valid_state_connects(
    client: AsyncClient, user: User, monkeypatch
):
    async def fake_exchange(code, u, d):
        u.dexcom_access_token = "encrypted"

    async def fake_sync(u, d):
        return 0

    monkeypatch.setattr(dexcom_svc, "exchange_code", fake_exchange)
    monkeypatch.setattr(dexcom_svc, "sync_glucose", fake_sync)

    state = create_state_token(user.id, "dexcom")
    resp = await client.get(
        "/auth/dexcom/callback", params={"code": "abc", "state": state}
    )
    assert resp.status_code == 303
    assert "provider=dexcom" in resp.headers["location"]
    assert "status=connected" in resp.headers["location"]


async def test_connections_dexcom_true_after_token_stored(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, user: User
):
    user.dexcom_access_token = "encrypted-token"
    await db.commit()

    resp = await client.get("/auth/connections", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["dexcom_connected"] is True
