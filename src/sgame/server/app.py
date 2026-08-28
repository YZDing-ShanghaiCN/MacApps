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

PROJECT_ROOT = Path(__file__).resolve().parents[3] / "sgame"
FRONTEND_DIR = PROJECT_ROOT / "frontend"

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


def html_response(path: Path) -> FileResponse:
    return FileResponse(path, headers={"Cache-Control": "no-cache"})


@app.get("/")
def read_root() -> FileResponse:
    return html_response(FRONTEND_DIR / "index.html")


@app.get("/schulte")
def read_schulte() -> FileResponse:
    return html_response(FRONTEND_DIR / "schulte" / "index.html")


@app.get("/minesweeper")
def read_minesweeper() -> FileResponse:
    return html_response(FRONTEND_DIR / "minesweeper" / "index.html")


@app.get("/pacman")
def read_pacman() -> FileResponse:
    return html_response(FRONTEND_DIR / "pacman" / "index.html")


@app.get("/2048")
def read_2048() -> FileResponse:
    return html_response(FRONTEND_DIR / "2048" / "index.html")


@app.get("/sw.js")
def read_service_worker() -> FileResponse:
    return FileResponse(
        FRONTEND_DIR / "sw.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
