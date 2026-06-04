import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.schemas.training_plan import TrainingPlanOut
from app.services import claude as claude_svc

router = APIRouter(prefix="/ai", tags=["ai"])


class InsightRequest(BaseModel):
    question: str


class InsightResponse(BaseModel):
    insight: str


class ChatMessage(BaseModel):
    # Literal constrains the role to exactly these two strings — Pydantic
    # rejects anything else with a 422 before our code ever runs.
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


class PlanRequest(BaseModel):
    week_start: str  # ISO date string, e.g. "2024-01-08"


@router.post("/insights", response_model=InsightResponse)
async def get_insights(
    payload: InsightRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Router's only job: parse request, call service, handle errors, return response
    try:
        insight = await claude_svc.get_insights(payload.question, current_user, db)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return InsightResponse(insight=insight)


@router.post("/chat")
async def chat(
    payload: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Streaming, multi-turn coaching chat.

    Returns Server-Sent Events: each frame is `data: {"text": "..."}` and the
    stream ends with `data: [DONE]`. We JSON-encode every chunk so newlines in
    Claude's output can't break the SSE framing (frames are split on blank
    lines).
    """
    # Validate up front, *before* we start streaming. Once a StreamingResponse
    # begins, the status code is already sent as 200 — we can't switch to 503
    # mid-stream. So both of these "can we even start?" checks happen here, and
    # only the actual token generation is deferred into the stream.
    if not settings.anthropic_api_key:
        raise HTTPException(status_code=503, detail="AI service is not configured")
    if not payload.messages or payload.messages[-1].role != "user":
        raise HTTPException(status_code=400, detail="messages must end with a user turn")

    history = [m.model_dump() for m in payload.messages]

    async def event_stream():
        try:
            async for chunk in claude_svc.stream_insights(history, current_user, db):
                yield f"data: {json.dumps({'text': chunk})}\n\n"
        except Exception as exc:  # noqa: BLE001 — surface the failure to the client
            # We're already mid-stream (HTTP 200 sent), so the only way to report
            # an error is as an in-band event the frontend knows to look for.
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
        yield "data: [DONE]\n\n"

    # NOTE: the get_db session stays open until this generator is exhausted —
    # FastAPI keeps yield-dependencies alive for the duration of a
    # StreamingResponse, which is exactly what we need since stream_insights
    # queries the DB. (This was a real footgun in older FastAPI versions.)
    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/training-plan", response_model=TrainingPlanOut)
async def generate_training_plan(
    payload: PlanRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        plan = await claude_svc.generate_training_plan(payload.week_start, current_user, db)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return plan
