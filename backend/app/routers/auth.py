from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_state_token,
    hash_password,
    verify_password,
    verify_state_token,
)
from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.schemas.user import Token, UserCreate, UserOut
from app.services import strava as strava_svc
from app.services import whoop as whoop_svc

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    existing = (
        await db.execute(select(User).where(User.email == payload.email))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(email=payload.email, hashed_password=hash_password(payload.password))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login", response_model=Token)
async def login(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    user = (
        await db.execute(select(User).where(User.email == payload.email))
    ).scalar_one_or_none()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return Token(access_token=create_access_token(str(user.id)))


# ── Strava OAuth ──────────────────────────────────────────────────────────────


@router.get("/strava/authorize")
async def strava_authorize(current_user: User = Depends(get_current_user)):
    """Build the URL we send the user to on Strava.

    This endpoint IS authenticated — our frontend calls it with the bearer
    token — so here we still know who the user is. We capture that identity in a
    signed `state` token that will survive the round-trip through Strava and
    come back to us on the callback (where no auth header is available).
    """
    state = create_state_token(current_user.id, "strava")
    url = (
        "https://www.strava.com/oauth/authorize"
        f"?client_id={settings.strava_client_id}"
        "&response_type=code"
        "&scope=activity:read_all"
        f"&redirect_uri={settings.strava_redirect_uri}"
        f"&state={state}"
    )
    return {"authorization_url": url}


@router.get("/strava/callback")
async def strava_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """OAuth redirect target. Strava sends the user's *browser* here, so there's
    no Authorization header to identify them — we recover the user from the
    signed `state` token instead. However it ends, we redirect the browser back
    to a frontend page with a status it can show the user.

    Note there's deliberately no `get_current_user` dependency here: requiring a
    bearer token would reject Strava's own redirect (that was the original bug).
    """
    frontend = settings.frontend_url.rstrip("/")

    def back(result: str) -> RedirectResponse:
        # 303 See Other: the right redirect after a side-effecting request — it
        # tells the browser to follow up with a plain GET to the frontend.
        return RedirectResponse(
            f"{frontend}/oauth/callback?provider=strava&status={result}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # User cancelled on Strava's consent screen, or the request is malformed —
    # either way there's nothing to exchange.
    if error or not code or not state:
        return back("error")

    # The heart of the fix: trust the signed state, not a (missing) auth header.
    user_id = verify_state_token(state, "strava")
    if user_id is None:
        return back("error")  # bad / expired / forged / wrong-provider state

    user = await db.get(User, user_id)
    if user is None:
        return back("error")

    # Exchanging the code for tokens is the make-or-break step. If it fails, the
    # connection genuinely didn't happen, so report error.
    try:
        await strava_svc.exchange_code(code, user, db)
    except ValueError:
        return back("error")

    # The initial sync is best-effort: the user is already connected, so a
    # transient Strava hiccup shouldn't report failure — fresh data will arrive
    # on the next manual sync.
    try:
        await strava_svc.sync_activities(user, db)
    except ValueError:
        pass

    return back("connected")


# ── WHOOP OAuth ───────────────────────────────────────────────────────────────


@router.get("/whoop/authorize")
async def whoop_authorize():
    from app.core.config import settings

    url = (
        "https://api.prod.whoop.com/oauth/oauth2/auth"
        f"?client_id={settings.whoop_client_id}"
        "&response_type=code"
        "&scope=read:recovery read:workout read:sleep read:profile"
        f"&redirect_uri={settings.whoop_redirect_uri}"
    )
    return {"authorization_url": url}


@router.get("/whoop/callback")
async def whoop_callback(
    code: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        await whoop_svc.exchange_code(code, current_user, db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "connected"}
