from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routers import ai, auth, recovery, workouts

app = FastAPI(
    title="Fitness Tracker API",
    description="Unified Whoop + Strava fitness tracker with AI insights",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(workouts.router)
app.include_router(recovery.router)
app.include_router(ai.router)


@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok", "environment": settings.environment}
