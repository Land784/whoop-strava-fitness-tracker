from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password, verify_password
from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.schemas.user import Token, UserCreate, UserOut
from app.services import strava as strava_svc
from app.services import whoop as whoop_svc

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    existing = (await db.execute(select(User).where(User.email == payload.email))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(email=payload.email, hashed_password=hash_password(payload.password))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login", response_model=Token)
async def login(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).where(User.email == payload.email))).scalar_one_or_none()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return Token(access_token=create_access_token(str(user.id)))


# ── Strava OAuth ──────────────────────────────────────────────────────────────

@router.get("/strava/authorize")
async def strava_authorize():
    from app.core.config import settings
    url = (
        "https://www.strava.com/oauth/authorize"
        f"?client_id={settings.strava_client_id}"
        "&response_type=code"
        "&scope=activity:read_all"
        f"&redirect_uri={settings.strava_redirect_uri}"
    )
    return {"authorization_url": url}


@router.get("/strava/callback")
async def strava_callback(
    code: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        await strava_svc.exchange_code(code, current_user, db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "connected"}


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
