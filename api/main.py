from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import settings
from api.routes import agenda_items, corrections, meetings

app = FastAPI(title="AirKing Data Tracker API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.include_router(agenda_items.router)
app.include_router(corrections.router)
app.include_router(meetings.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
