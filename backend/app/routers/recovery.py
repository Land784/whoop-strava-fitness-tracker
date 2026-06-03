from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.recovery import RecoveryScore
from app.models.user import User
from app.schemas.recovery import RecoveryCreate, RecoveryOut

router = APIRouter(prefix="/recovery", tags=["recovery"])


@router.get("/", response_model=list[RecoveryOut])
async def list_recovery(
    skip: int = 0,
    limit: int = 30,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(RecoveryScore)
        .where(RecoveryScore.user_id == current_user.id)
        .order_by(RecoveryScore.date.desc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()


@router.post("/", response_model=RecoveryOut, status_code=status.HTTP_201_CREATED)
async def create_recovery(
    payload: RecoveryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing = (
        await db.execute(
            select(RecoveryScore).where(
                RecoveryScore.user_id == current_user.id,
                RecoveryScore.date == payload.date,
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Recovery entry for this date already exists")

    record = RecoveryScore(**payload.model_dump(), user_id=current_user.id)
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


@router.get("/{record_id}", response_model=RecoveryOut)
async def get_recovery(
    record_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    record = (
        await db.execute(
            select(RecoveryScore).where(
                RecoveryScore.id == record_id,
                RecoveryScore.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Recovery record not found")
    return record
