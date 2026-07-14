from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys
from typing import Any

from fastapi.testclient import TestClient

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from gomoku import config
from gomoku.server import routes
from gomoku.server.app import app


def request(method: str, path: str, json_body: dict | None = None) -> dict[str, Any]:
    body = json.dumps(json_body).encode("utf-8") if json_body is not None else b""
    headers = [(b"host", b"testserver")]
    if json_body is not None:
        headers.append((b"content-type", b"application/json"))

    messages: list[dict[str, Any]] = []
    request_sent = False

    async def receive() -> dict[str, Any]:
        nonlocal request_sent
        if request_sent:
            return {"type": "http.disconnect"}
        request_sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": headers,
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }

    asyncio.run(app(scope, receive, send))

    start = next(message for message in messages if message["type"] == "http.response.start")
    response_body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    )
    return {
        "status": start["status"],
        "body": json.loads(response_body.decode("utf-8")) if response_body else None,
    }


def setup_function() -> None:
    routes.set_current_mode(config.MODE_LOCAL_2P)
    routes.game.reset()


def test_health_returns_ok() -> None:
    response = request("GET", "/health")

    assert response["status"] == 200
    assert response["body"] == {"status": "ok"}


def test_state_contains_web_fields() -> None:
    response = request("GET", "/api/state")

    assert response["status"] == 200
    assert {
        "board",
        "current_player",
        "winner",
        "game_over",
        "move_count",
        "current_player_name",
        "winner_name",
        "winning_line",
        "timer_running",
        "time_spent",
        "last_move",
        "mode",
        "ai_player",
    }.issubset(response["body"])
    assert response["body"]["mode"] == config.MODE_LOCAL_2P
    assert response["body"]["ai_player"] is None


def test_start_enables_cumulative_timer() -> None:
    response = request("POST", "/api/start")

    assert response["status"] == 200
    assert response["body"]["timer_running"] is True


def test_create_private_room_returns_private_owner_and_invite_links() -> None:
    response = request("POST", "/api/rooms")

    assert response["status"] == 201
    assert response["body"]["room_id"]
    assert "/room/" in response["body"]["owner_url"]
    assert "#token=" in response["body"]["owner_url"]
    assert "?token=" not in response["body"]["owner_url"]
    assert response["body"]["owner_url"] != response["body"]["invite_url"]


def test_create_private_room_rejects_loopback_link_without_public_base_url() -> None:
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        response = client.post("/api/rooms")

    assert response.status_code == 400
    assert "run_quick_tunnel.py" in response.json()["error"]


def test_api_docs_are_disabled_by_default() -> None:
    response = request("GET", "/docs")

    assert response["status"] == 404


def test_pwa_assets_are_served() -> None:
    with TestClient(app) as client:
        manifest = client.get("/static/manifest.webmanifest")
        service_worker = client.get("/sw.js")

    assert manifest.status_code == 200
    assert "私人五子棋" in manifest.text
    assert service_worker.status_code == 200
    assert "gomoku-shell-v0.1.4" in service_worker.text


def test_move_returns_updated_state() -> None:
    response = request("POST", "/api/move", {"row": 7, "col": 7})

    assert response["status"] == 200
    assert response["body"]["move_count"] == 1
    assert response["body"]["last_move"] == {"row": 7, "col": 7, "player": 1}


def test_undo_returns_empty_state() -> None:
    request("POST", "/api/move", {"row": 7, "col": 7})

    response = request("POST", "/api/undo")

    assert response["status"] == 200
    assert response["body"]["move_count"] == 0
    assert response["body"]["last_move"] is None


def test_reset_returns_initial_state() -> None:
    request("POST", "/api/move", {"row": 7, "col": 7})

    response = request("POST", "/api/reset")

    assert response["status"] == 200
    assert response["body"]["move_count"] == 0
    assert response["body"]["game_over"] is False
    assert response["body"]["mode"] == config.MODE_LOCAL_2P


def test_reset_can_change_mode() -> None:
    request("POST", "/api/move", {"row": 7, "col": 7})

    response = request("POST", "/api/reset", {"mode": config.MODE_VS_AI})

    assert response["status"] == 200
    assert response["body"]["move_count"] == 0
    assert response["body"]["mode"] == config.MODE_VS_AI
    assert response["body"]["ai_player"] == 2


def test_mode_endpoint_switches_mode_and_resets_game() -> None:
    request("POST", "/api/move", {"row": 7, "col": 7})

    response = request("POST", "/api/mode", {"mode": config.MODE_VS_AI})

    assert response["status"] == 200
    assert response["body"]["move_count"] == 0
    assert response["body"]["mode"] == config.MODE_VS_AI
    assert response["body"]["ai_player"] == 2


def test_invalid_move_returns_error() -> None:
    response = request("POST", "/api/move", {"row": 99, "col": 99})

    assert response["status"] == 400
    assert "error" in response["body"]


def test_invalid_mode_returns_error() -> None:
    response = request("POST", "/api/mode", {"mode": "bad_mode"})

    assert response["status"] == 400
    assert "error" in response["body"]
