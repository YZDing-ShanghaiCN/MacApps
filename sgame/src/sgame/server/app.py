from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from sgame import config

app = FastAPI(
    title="sgame API",
    version=config.APP_VERSION,
    docs_url="/docs" if config.ENABLE_API_DOCS else None,
    redoc_url="/redoc" if config.ENABLE_API_DOCS else None,
    openapi_url="/openapi.json" if config.ENABLE_API_DOCS else None,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_DIR = PROJECT_ROOT / "frontend"

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/")
def read_root() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/schulte")
def read_schulte() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "schulte" / "index.html")


@app.get("/minesweeper")
def read_minesweeper() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "minesweeper" / "index.html")


@app.get("/pacman")
def read_pacman() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "pacman" / "index.html")


@app.get("/sw.js")
def read_service_worker() -> FileResponse:
    return FileResponse(
        FRONTEND_DIR / "sw.js",
        media_type="application/javascript",
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
