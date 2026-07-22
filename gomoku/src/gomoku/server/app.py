import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from gomoku import config
from gomoku.server.rooms import room_manager, router as room_router
from gomoku.server.routes import router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    cleanup_task = asyncio.create_task(_cleanup_expired_rooms())
    try:
        yield
    finally:
        cleanup_task.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup_task


async def _cleanup_expired_rooms() -> None:
    while True:
        await asyncio.sleep(config.ROOM_CLEANUP_INTERVAL_SECONDS)
        await room_manager.cleanup_expired_rooms()


app = FastAPI(
    title="Gomoku API",
    version=config.APP_VERSION,
    docs_url="/docs" if config.ENABLE_API_DOCS else None,
    redoc_url="/redoc" if config.ENABLE_API_DOCS else None,
    openapi_url="/openapi.json" if config.ENABLE_API_DOCS else None,
    lifespan=lifespan,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_DIR = PROJECT_ROOT / "frontend"

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
app.include_router(router)
app.include_router(room_router)


@app.get("/")
def read_root() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/room/{room_id}")
def read_room(room_id: str) -> FileResponse:
    return FileResponse(FRONTEND_DIR / "room.html")


@app.get("/sw.js")
def read_service_worker() -> FileResponse:
    return FileResponse(
        FRONTEND_DIR / "sw.js",
        media_type="application/javascript",
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
