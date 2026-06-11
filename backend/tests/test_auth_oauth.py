"""HTTP-level tests for the Strava OAuth endpoints and the connections status.

The genuine OAuth round-trip needs a live Strava approval, so we test the parts
we control: that authorize is auth-gated and embeds a signed state, and that the
callback trusts the state (rejecting missing/forged ones) without needing an auth
header. The token-exchange + sync services are stubbed so nothing hits Strava.
"""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_state_token
from app.models.user import User
from app.services import strava as strava_svc


# ── authorize ─────────────────────────────────────────────────────────────────

async def test_authorize_requires_auth(client: AsyncClient):
    resp = await client.get("/auth/strava/authorize")
    # HTTPBearer returns 403 when the Authorization header is absent.
    assert resp.status_code in (401, 403)


async def test_authorize_returns_url_with_state(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/auth/strava/authorize", headers=auth_headers)
    assert resp.status_code == 200
    url = resp.json()["authorization_url"]
    assert "www.strava.com/oauth/authorize" in url
    assert "state=" in url


# ── callback ──────────────────────────────────────────────────────────────────
# The test client does not follow redirects by default, so we inspect the 303
# and its Location header directly.

async def test_callback_missing_state_redirects_to_error(client: AsyncClient):
    resp = await client.get("/auth/strava/callback", params={"code": "abc"})
    assert resp.status_code == 303
    assert "status=error" in resp.headers["location"]


async def test_callback_forged_state_redirects_to_error(client: AsyncClient):
    resp = await client.get(
        "/auth/strava/callback", params={"code": "abc", "state": "forged"}
    )
    assert resp.status_code == 303
    assert "status=error" in resp.headers["location"]


async def test_callback_valid_state_connects(
    client: AsyncClient, user: User, monkeypatch
):
    # Stub the network-touching service calls so nothing hits Strava.
    async def fake_exchange(code, u, d):
        u.strava_access_token = "encrypted"

    async def fake_sync(u, d):
        return 0

    monkeypatch.setattr(strava_svc, "exchange_code", fake_exchange)
    monkeypatch.setattr(strava_svc, "sync_activities", fake_sync)

    state = create_state_token(user.id, "strava")
    resp = await client.get(
        "/auth/strava/callback", params={"code": "abc", "state": state}
    )
    assert resp.status_code == 303
    assert "status=connected" in resp.headers["location"]


# ── current user (/auth/me) ─────────────────────────────────────────────────────
# The frontend hits this on boot to validate a stored token. We test the two
# branches that drive that logic: a valid token returns the user; a missing
# token is rejected (so the client knows to clear the session and show login).

async def test_me_requires_auth(client: AsyncClient):
    resp = await client.get("/auth/me")
    # HTTPBearer returns 403 when the Authorization header is absent.
    assert resp.status_code in (401, 403)


async def test_me_returns_current_user(
    client: AsyncClient, auth_headers: dict, user: User
):
    resp = await client.get("/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == user.id
    assert body["email"] == user.email
    # Tokens must never leak through a user-facing response.
    assert "hashed_password" not in body
    assert "strava_access_token" not in body


# ── connections status ────────────────────────────────────────────────────────

async def test_connections_requires_auth(client: AsyncClient):
    resp = await client.get("/auth/connections")
    assert resp.status_code in (401, 403)


async def test_connections_false_when_not_connected(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.get("/auth/connections", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == {
        "strava_connected": False,
        "whoop_connected": False,
        "dexcom_connected": False,
    }


async def test_connections_true_after_token_stored(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, user: User
):
    user.strava_access_token = "encrypted-token"
    await db.commit()

    resp = await client.get("/auth/connections", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["strava_connected"] is True
