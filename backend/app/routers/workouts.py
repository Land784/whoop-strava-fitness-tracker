from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.models.workout import Workout
from app.schemas.workout import WorkoutCreate, WorkoutOut
from app.services import sync as sync_svc

router = APIRouter(prefix="/workouts", tags=["workouts"])


@router.get("/", response_model=list[WorkoutOut])
async def list_workouts(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Every query filters by user_id — this is the multi-tenant isolation boundary
    result = await db.execute(
        select(Workout)
        .where(Workout.user_id == current_user.id)
        .order_by(Workout.date.desc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()


@router.post("/", response_model=WorkoutOut, status_code=status.HTTP_201_CREATED)
async def create_workout(
    payload: WorkoutCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workout = Workout(**payload.model_dump(), user_id=current_user.id)
    db.add(workout)
    await db.commit()
    await db.refresh(workout)
    return workout


@router.get("/{workout_id}", response_model=WorkoutOut)
async def get_workout(
    workout_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workout = (
        await db.execute(
            select(Workout).where(Workout.id == workout_id, Workout.user_id == current_user.id)
        )
    ).scalar_one_or_none()
    if not workout:
        raise HTTPException(status_code=404, detail="Workout not found")
    return workout


@router.delete("/{workout_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workout(
    workout_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workout = (
        await db.execute(
            select(Workout).where(Workout.id == workout_id, Workout.user_id == current_user.id)
        )
    ).scalar_one_or_none()
    if not workout:
        raise HTTPException(status_code=404, detail="Workout not found")
    await db.delete(workout)
    await db.commit()


@router.post("/sync", response_model=dict)
async def sync_workouts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trigger a full sync from all connected sources (Strava + WHOOP)."""
    results = await sync_svc.sync_all(current_user, db)
    return results
