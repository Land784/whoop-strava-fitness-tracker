from datetime import datetime

from pydantic import BaseModel, EmailStr


class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    email: str
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    user_id: str | None = None


class ConnectionStatus(BaseModel):
    """Which external providers the user has connected. Booleans only — we never
    expose the stored tokens themselves in an API response."""

    strava_connected: bool
    whoop_connected: bool
    dexcom_connected: bool
