from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Build the Fernet cipher once, at import time, from the key in the environment.
# Doing it here (not per-call) means a bad/missing key fails fast when the app
# starts, not on the first token we try to store. The key never lives in the
# database or the code — only in the environment — so a leaked DB dump can't be
# decrypted on its own.
_fernet = Fernet(settings.token_encryption_key)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ── OAuth token encryption ────────────────────────────────────────────────────
# Hashing (above) is one-way: we can check a password but never recover it.
# Tokens are different — we must get the *original* value back to call Strava/
# WHOOP, so we need reversible *encryption*, not hashing. That's what Fernet is.


def encrypt_token(plaintext: str) -> str:
    """Encrypt an OAuth token for storage at rest.

    Fernet works on bytes, so we encode in / decode out. The result is URL-safe
    base64 text, which drops straight into our existing Text columns.
    """
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    """Reverse of encrypt_token.

    Raises cryptography.fernet.InvalidToken if the value was tampered with or
    was encrypted under a different key — i.e. it fails loudly rather than
    handing back corrupted data.
    """
    return _fernet.decrypt(ciphertext.encode()).decode()


def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    return jwt.encode(
        {"sub": subject, "exp": expire},
        settings.secret_key,
        algorithm=settings.algorithm,
    )


def decode_token(token: str) -> str | None:
    try:
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[settings.algorithm]
        )
        return payload.get("sub")
    except JWTError:
        return None


# ── OAuth `state` tokens ──────────────────────────────────────────────────────
# The OAuth callback is a *browser redirect* from the provider, so it can't send
# our usual Authorization header. We instead carry the user's identity through
# the round-trip in the OAuth `state` parameter, as a short-lived signed token.
# Because it's signed with our SECRET_KEY, only our server can mint a valid one
# — that's what makes the callback safe from forgery (CSRF).


def create_state_token(user_id: int, provider: str) -> str:
    """Mint a signed `state` token for an OAuth authorize URL.

    Encodes *who* is connecting and *which* provider, plus a `purpose` claim so
    this can never be confused with a login token.
    """
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.oauth_state_expire_minutes
    )
    return jwt.encode(
        {
            "sub": str(user_id),
            "provider": provider,
            "purpose": "oauth_state",
            "exp": expire,
        },
        settings.secret_key,
        algorithm=settings.algorithm,
    )


def verify_state_token(token: str, provider: str) -> int | None:
    """Verify a `state` token and return the user_id it was minted for.

    Returns None — rather than raising — if the token is invalid, expired, for
    the wrong provider, or not actually a state token. The caller (a router)
    decides what HTTP response that maps to, keeping HTTP concerns out of here.
    """
    try:
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[settings.algorithm]
        )
    except JWTError:
        # Covers a bad signature, a tampered token, AND expiry (jose raises
        # ExpiredSignatureError, a subclass of JWTError) — all "not valid".
        return None

    # Defence in depth: reject anything that isn't specifically a state token
    # for this exact provider, even if it's otherwise correctly signed.
    if payload.get("purpose") != "oauth_state":
        return None
    if payload.get("provider") != provider:
        return None

    sub = payload.get("sub")
    return int(sub) if sub is not None else None
