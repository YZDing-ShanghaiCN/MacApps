from __future__ import annotations

import asyncio
from dataclasses import replace
import json
from pathlib import Path
import sys
import time
from typing import Any

from fastapi.testclient import TestClient

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from gomoku import config
from gomoku.ai.normal_ai import NormalAI
from gomoku.ai.normal_ai_config import DEFAULT_NORMAL_AI_CONFIG
from gomoku.core.enums import Player
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
    routes.set_human_color(config.DEFAULT_HUMAN_COLOR)
    routes.set_current_difficulty(config.AI_DIFFICULTY_SIMPLE)
    routes.cancel_pending_ai()
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
        "ai_difficulty",
        "ai_thinking",
        "ai_error",
        "ai_search_stats",
        "ai_decision",
        "human_player",
        "human_color_choice",
    }.issubset(response["body"])
    assert response["body"]["mode"] == config.MODE_LOCAL_2P
    assert response["body"]["ai_player"] is None
    assert response["body"]["size"] == config.BOARD_SIZE
    assert len(response["body"]["board"]) == config.BOARD_SIZE
    assert all(
        len(row) == config.BOARD_SIZE
        for row in response["body"]["board"]
    )


def test_debug_position_exports_reproducible_normal_ai_snapshot() -> None:
    routes.set_current_mode(config.MODE_VS_AI)
    routes.set_current_difficulty(config.AI_DIFFICULTY_NORMAL)
    routes.game.make_move(7, 7)

    response = request("GET", "/api/debug-position")

    assert response["status"] == 200
    snapshot = response["body"]
    assert snapshot["schema_version"] == 1
    assert snapshot["app_version"] == config.APP_VERSION
    assert snapshot["position"]["board"][7][7] == int(Player.BLACK)
    assert snapshot["position"]["move_history"] == [
        {"row": 7, "col": 7, "player": int(Player.BLACK)}
    ]
    assert snapshot["game"]["ai_difficulty"] == config.AI_DIFFICULTY_NORMAL
    assert snapshot["normal_ai"]["config"]["time_limit_ms"] == 800
    assert snapshot["normal_ai"]["search_stats"]["nodes"] == 0


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
    assert "gomoku-shell-v0.3.4" in service_worker.text


def test_move_returns_updated_state() -> None:
    response = request("POST", "/api/move", {"row": 7, "col": 7})

    assert response["status"] == 200
    assert response["body"]["move_count"] == 1
    assert response["body"]["last_move"] == {"row": 7, "col": 7, "player": 1}


def test_web_board_accepts_a_move_in_the_outermost_row_and_column() -> None:
    response = request("POST", "/api/move", {"row": 14, "col": 14})

    assert response["status"] == 200
    assert response["body"]["board"][14][14] == 1


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


def test_difficulty_endpoint_selects_normal_and_reset_preserves_it() -> None:
    response = request(
        "POST",
        "/api/difficulty",
        {"difficulty": config.AI_DIFFICULTY_NORMAL},
    )
    assert response["status"] == 200
    assert response["body"]["ai_difficulty"] == config.AI_DIFFICULTY_NORMAL

    reset_response = request("POST", "/api/reset")
    assert reset_response["body"]["ai_difficulty"] == config.AI_DIFFICULTY_NORMAL


def test_hard_difficulty_remains_unavailable() -> None:
    response = request(
        "POST",
        "/api/difficulty",
        {"difficulty": config.AI_DIFFICULTY_HARD},
    )
    assert response["status"] == 400


def test_human_can_select_white_and_ai_opens_as_black_after_start() -> None:
    request("POST", "/api/mode", {"mode": config.MODE_VS_AI})
    color_response = request(
        "POST",
        "/api/ai-color",
        {"human_color": config.HUMAN_COLOR_WHITE},
    )

    assert color_response["status"] == 200
    assert color_response["body"]["human_player"] == int(Player.WHITE)
    assert color_response["body"]["ai_player"] == int(Player.BLACK)
    assert color_response["body"]["move_count"] == 0

    started = request("POST", "/api/start")
    assert started["body"]["ai_thinking"] is True
    deadline = time.monotonic() + 1
    state = request("GET", "/api/state")["body"]
    while state["ai_thinking"] and time.monotonic() < deadline:
        time.sleep(0.01)
        state = request("GET", "/api/state")["body"]
    assert state["move_count"] == 1
    assert state["last_move"]["player"] == int(Player.BLACK)
    assert state["current_player"] == int(Player.WHITE)


def test_selected_human_color_survives_reset() -> None:
    request("POST", "/api/mode", {"mode": config.MODE_VS_AI})
    request(
        "POST",
        "/api/ai-color",
        {"human_color": config.HUMAN_COLOR_WHITE},
    )

    reset = request("POST", "/api/reset")

    assert reset["body"]["human_color_choice"] == config.HUMAN_COLOR_WHITE
    assert reset["body"]["human_player"] == int(Player.WHITE)
    assert reset["body"]["ai_player"] == int(Player.BLACK)


def test_invalid_human_color_is_rejected() -> None:
    response = request("POST", "/api/ai-color", {"human_color": "green"})
    assert response["status"] == 400


def test_simple_ai_decision_is_published_after_background_move() -> None:
    request("POST", "/api/mode", {"mode": config.MODE_VS_AI})
    request("POST", "/api/start")
    moved = request("POST", "/api/move", {"row": 7, "col": 7})
    assert moved["body"]["ai_thinking"] is True
    deadline = time.monotonic() + 1
    state = request("GET", "/api/state")["body"]
    while state["ai_thinking"] and time.monotonic() < deadline:
        time.sleep(0.01)
        state = request("GET", "/api/state")["body"]
    assert state["ai_decision"]["reason"] != "not_searched"
    assert state["ai_decision"]["candidates"]


def test_move_is_rejected_while_ai_is_thinking() -> None:
    routes.default_session.ai_thinking = True
    try:
        response = request("POST", "/api/move", {"row": 7, "col": 7})
    finally:
        routes.default_session.ai_thinking = False
    assert response["status"] == 409


def test_local_game_sessions_are_isolated() -> None:
    first_id = "session_first"
    second_id = "session_second"
    routes.reset_game(None, first_id)
    routes.reset_game(None, second_id)
    routes.make_move({"row": 7, "col": 7}, first_id)

    first = routes.get_state(first_id)
    second = routes.get_state(second_id)
    assert first["board"][7][7] == 1
    assert second["board"][7][7] == 0


def test_normal_ai_runs_in_background_and_can_be_cancelled_by_reset() -> None:
    session_id = "session_normal"
    session = routes.get_session(session_id)
    with session.lock:
        routes.cancel_pending_ai(session)
        routes.set_current_mode(config.MODE_VS_AI, session)
        routes.set_current_difficulty(config.AI_DIFFICULTY_NORMAL, session)
        session.game.reset()

    response = routes.make_move({"row": 7, "col": 7}, session_id)
    assert response["move_count"] == 1
    assert response["ai_thinking"] is True

    reset = routes.reset_game(None, session_id)
    assert reset["move_count"] == 0
    assert reset["ai_thinking"] is False
    time.sleep(0.03)
    assert routes.get_state(session_id)["move_count"] == 0


def test_normal_ai_background_result_and_stats_are_published() -> None:
    session_id = "session_normal_result"
    session = routes.get_session(session_id)
    with session.lock:
        routes.cancel_pending_ai(session)
        routes.set_current_mode(config.MODE_VS_AI, session)
        routes.set_current_difficulty(config.AI_DIFFICULTY_NORMAL, session)
        session.ai = NormalAI(
            Player.WHITE,
            config=replace(
                DEFAULT_NORMAL_AI_CONFIG,
                time_limit_ms=80,
                max_depth=2,
                enable_vcf=False,
            ),
        )
        session.game.reset()

    response = routes.make_move({"row": 7, "col": 7}, session_id)
    assert response["ai_thinking"] is True

    deadline = time.monotonic() + 1.0
    state = routes.get_state(session_id)
    while state["ai_thinking"] and time.monotonic() < deadline:
        time.sleep(0.01)
        state = routes.get_state(session_id)

    assert state["ai_thinking"] is False
    assert state["ai_error"] is None
    assert state["move_count"] == 2
    assert state["ai_search_stats"]["nodes"] >= 0
    assert state["ai_search_stats"]["elapsed_ms"] >= 0
