from datetime import date, datetime

from pydantic import BaseModel


class DailyBriefingOut(BaseModel):
    """The dashboard daily briefing, as three ready-to-render sections.

    We deliberately do NOT expose the raw content_json column — the API returns
    the parsed fields so the frontend never has to know how we store it.
    """

    date: date
    generated_at: datetime
    recovery: str
    state: str
    recommended_workout: str
