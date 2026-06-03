from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str

    # Auth
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    # How long an OAuth `state` token stays valid. Only needs to cover the gap
    # between clicking "Connect" and finishing approval on the provider's site.
    oauth_state_expire_minutes: int = 10

    # Whoop
    whoop_client_id: str = ""
    whoop_client_secret: str = ""
    whoop_redirect_uri: str = "http://localhost:8000/auth/whoop/callback"

    # Strava
    strava_client_id: str = ""
    strava_client_secret: str = ""
    strava_redirect_uri: str = "http://localhost:8000/auth/strava/callback"

    # AI
    anthropic_api_key: str = ""

    # Token encryption — Fernet key for encrypting OAuth tokens at rest.
    # Intentionally required (no default): the app should refuse to start rather
    # than silently fall back to storing tokens in plaintext. Generate one with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    token_encryption_key: str

    # App
    environment: str = "development"
    # Base URL of the frontend. Used to redirect the browser back to a page it
    # controls after an OAuth callback finishes on the backend.
    frontend_url: str = "http://localhost:3000"


settings = Settings()
