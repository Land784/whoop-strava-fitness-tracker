"""Unit tests for the security-critical pure logic: token encryption and the
OAuth `state` tokens. No DB or network — just the functions in core/security.py.
"""

import pytest
from cryptography.fernet import InvalidToken

from app.core import security
from app.core.security import (
    create_access_token,
    create_state_token,
    decrypt_token,
    encrypt_token,
    verify_state_token,
)


# ── Token encryption (Fernet) ─────────────────────────────────────────────────

def test_encrypt_round_trip():
    """Encrypting then decrypting returns the original token unchanged."""
    secret = "strava_access_token_abc123"
    ciphertext = encrypt_token(secret)
    assert ciphertext != secret  # stored value is not the plaintext
    assert decrypt_token(ciphertext) == secret


def test_decrypt_rejects_tampering():
    """A modified ciphertext fails loudly instead of returning corrupt data."""
    ciphertext = encrypt_token("secret")
    tampered = ("A" if ciphertext[0] != "A" else "B") + ciphertext[1:]
    with pytest.raises(InvalidToken):
        decrypt_token(tampered)


# ── OAuth state tokens ────────────────────────────────────────────────────────

def test_state_round_trip():
    """A freshly minted state token verifies and yields the user id."""
    token = create_state_token(42, "strava")
    assert verify_state_token(token, "strava") == 42


def test_state_wrong_provider_rejected():
    """A Strava state must not validate against the WHOOP callback."""
    token = create_state_token(42, "strava")
    assert verify_state_token(token, "whoop") is None


def test_state_forged_rejected():
    """Garbage / unsigned input is rejected."""
    assert verify_state_token("not.a.real.token", "strava") is None


def test_login_token_not_accepted_as_state():
    """A valid login JWT (no `purpose` claim) must not pass as a state token."""
    login = create_access_token("42")
    assert verify_state_token(login, "strava") is None


def test_state_expired_rejected(monkeypatch):
    """An expired state token is rejected."""
    monkeypatch.setattr(security.settings, "oauth_state_expire_minutes", -1)
    token = create_state_token(42, "strava")
    assert verify_state_token(token, "strava") is None
