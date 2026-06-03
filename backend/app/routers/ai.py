from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.schemas.training_plan import TrainingPlanOut
from app.services import claude as claude_svc

router = APIRouter(prefix="/ai", tags=["ai"])


class InsightRequest(BaseModel):
    question: str


class InsightResponse(BaseModel):
    insight: str


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
