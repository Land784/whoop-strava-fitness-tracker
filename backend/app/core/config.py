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
    # Centralised so the model can be bumped in one place (or overridden via
    # env) instead of being hardcoded at each call site.
    #
    # Two models on purpose:
    #   - claude_model: the stronger Sonnet, used for the weekly training plan.
    #     It runs rarely (once a week) and benefits from better reasoning.
    #   - claude_chat_model: the cheaper/faster Haiku, used for the chat
    #     insights endpoint. That call is high-frequency and "look at my data,
    #     give advice" doesn't need Sonnet-level reasoning. Haiku is ~3x cheaper
    #     per token, so this is where the cost savings actually land.
    claude_model: str = "claude-sonnet-4-6"
    claude_chat_model: str = "claude-haiku-4-5-20251001"

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
