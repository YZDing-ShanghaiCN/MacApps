from __future__ import annotations

from pathlib import Path
import sys

SRC_DIR = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SRC_DIR))

from fastapi.testclient import TestClient

from sgame import config
from sgame.server.app import app


client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_portal_page_contains_game_links() -> None:
    response = client.get("/")

    assert response.status_code == 200
    text = response.text
    assert 'href="/schulte"' in text
    assert 'href="/minesweeper"' in text
    assert 'href="/pacman"' in text


def test_schulte_page_served() -> None:
    response = client.get("/schulte")

    assert response.status_code == 200
    assert "舒尔特方格" in response.text
    assert '<div id="grid"' in response.text


def test_minesweeper_page_served() -> None:
    response = client.get("/minesweeper")

    assert response.status_code == 200
    assert "扫雷" in response.text
    assert '<div id="board"' in response.text


def test_pacman_page_served() -> None:
    response = client.get("/pacman")

    assert response.status_code == 200
    assert "吃豆人" in response.text
    assert '<canvas id="game"' in response.text


def test_trailing_slash_redirects() -> None:
    response = client.get("/pacman/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"].endswith("/pacman")


def test_static_css_served() -> None:
    response = client.get("/static/style.css")

    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]


def test_static_schulte_js_served() -> None:
    response = client.get("/static/schulte/schulte.js")

    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]


def test_static_minesweeper_js_served() -> None:
    response = client.get("/static/minesweeper/minesweeper.js")

    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]


def test_static_pacman_js_served() -> None:
    response = client.get("/static/pacman/pacman.js")

    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]


def test_sw_js_served() -> None:
    response = client.get("/sw.js")

    assert response.status_code == 200
    assert "application/javascript" in response.headers["content-type"]
    assert "sgame-shell-v" in response.text


def test_api_docs_disabled_by_default() -> None:
    response = client.get("/docs")

    assert response.status_code == 404


def test_unknown_page_returns_404() -> None:
    response = client.get("/nonexistent")

    assert response.status_code == 404


def test_manifest_served() -> None:
    response = client.get("/static/manifest.webmanifest")

    assert response.status_code == 200
    assert "sgame" in response.text


def test_icon_served() -> None:
    response = client.get("/static/icon.svg")

    assert response.status_code == 200
    assert "image/svg+xml" in response.headers["content-type"]