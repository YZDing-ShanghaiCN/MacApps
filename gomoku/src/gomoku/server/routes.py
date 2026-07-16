from __future__ import annotations

import threading

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from gomoku import config
from gomoku.adapters.web_adapter import serialize_game_state
from gomoku.ai.factory import create_ai
from gomoku.core.enums import Player
from gomoku.core.exceptions import GameOverError, InvalidMoveError
from gomoku.core.game import GomokuGame


router = APIRouter(prefix="/api")
game = GomokuGame()
current_mode = config.DEFAULT_MODE
AI_PLAYER = Player.WHITE
current_ai_difficulty = config.DEFAULT_AI_DIFFICULTY
ai = create_ai(current_ai_difficulty, AI_PLAYER)
ai_thinking = False
state_lock = threading.RLock()


def active_ai_player() -> Player | None:
    if current_mode == config.MODE_VS_AI:
        return AI_PLAYER
    return None


def state_response() -> dict:
    return serialize_game_state(
        game,
        mode=current_mode,
        ai_player=active_ai_player(),
        ai_difficulty=current_ai_difficulty,
        ai_thinking=ai_thinking,
    )


def validate_mode(mode: object) -> str | None:
    if isinstance(mode, str) and mode in config.VALID_MODES:
        return mode
    return None


def validate_difficulty(difficulty: object) -> str | None:
    if (
        isinstance(difficulty, str)
        and difficulty in config.AVAILABLE_AI_DIFFICULTIES
    ):
        return difficulty
    return None


def invalid_mode_response() -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={
            "error": (
                "Mode must be one of: "
                f"{', '.join(config.VALID_MODES)}."
            )
        },
    )


def invalid_difficulty_response() -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={
            "error": (
                "AI difficulty must be one of: "
                f"{', '.join(config.AVAILABLE_AI_DIFFICULTIES)}."
            )
        },
    )


def ai_busy_response() -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={"error": "AI is currently thinking."},
    )


def set_current_mode(mode: str) -> None:
    global current_mode
    current_mode = mode


def set_current_difficulty(difficulty: str) -> None:
    global ai, current_ai_difficulty
    if difficulty not in config.AVAILABLE_AI_DIFFICULTIES:
        raise ValueError(f"AI difficulty is not available: {difficulty}.")
    current_ai_difficulty = difficulty
    ai = create_ai(difficulty, AI_PLAYER)


def maybe_play_ai_move(last_opponent_move: tuple[int, int]) -> None:
    global ai_thinking
    if current_mode != config.MODE_VS_AI:
        return

    if game.game_over or game.current_player != AI_PLAYER:
        return

    selected_ai = ai
    try:
        ai_move = selected_ai.choose_move(
            game.board,
            last_opponent_move=last_opponent_move,
        )
        with state_lock:
            if ai_move is not None:
                game.make_move(*ai_move)
    finally:
        with state_lock:
            ai_thinking = False


def undo_for_current_mode() -> None:
    if current_mode == config.MODE_VS_AI:
        if game.undo() and game.current_player == AI_PLAYER:
            game.undo()
        return

    game.undo()


@router.get("/state")
def get_state() -> dict:
    with state_lock:
        return state_response()


@router.post("/move")
def make_move(payload: dict = Body(...)):
    global ai_thinking
    try:
        row = int(payload["row"])
        col = int(payload["col"])
    except (KeyError, TypeError, ValueError):
        return JSONResponse(
            status_code=400,
            content={"error": "Move request must include integer row and col."},
        )

    with state_lock:
        if ai_thinking:
            return ai_busy_response()
        if current_mode == config.MODE_VS_AI and game.current_player == AI_PLAYER:
            return ai_busy_response()
        try:
            game.make_move(row, col)
        except InvalidMoveError as exc:
            return JSONResponse(status_code=400, content={"error": str(exc)})
        except GameOverError as exc:
            return JSONResponse(status_code=400, content={"error": str(exc)})
        should_play_ai = (
            current_mode == config.MODE_VS_AI
            and not game.game_over
            and game.current_player == AI_PLAYER
        )
        if should_play_ai:
            ai_thinking = True

    if should_play_ai:
        maybe_play_ai_move((row, col))

    with state_lock:
        return state_response()


@router.post("/reset")
def reset_game(payload: dict | None = Body(default=None)):
    with state_lock:
        if ai_thinking:
            return ai_busy_response()
        if payload is not None:
            if not isinstance(payload, dict):
                return JSONResponse(
                    status_code=400,
                    content={"error": "Reset request body must be an object."},
                )

            if "mode" in payload:
                requested_mode = validate_mode(payload["mode"])
                if requested_mode is None:
                    return invalid_mode_response()
                set_current_mode(requested_mode)

            if "ai_difficulty" in payload:
                requested_difficulty = validate_difficulty(
                    payload["ai_difficulty"]
                )
                if requested_difficulty is None:
                    return invalid_difficulty_response()
                set_current_difficulty(requested_difficulty)

        game.reset()
        return state_response()


@router.post("/start")
def start_game() -> dict:
    with state_lock:
        if ai_thinking:
            return ai_busy_response()
        game.start_timer()
        return state_response()


@router.post("/undo")
def undo_move() -> dict:
    with state_lock:
        if ai_thinking:
            return ai_busy_response()
        undo_for_current_mode()
        return state_response()


@router.post("/mode")
def change_mode(payload: dict = Body(...)):
    try:
        requested_mode = validate_mode(payload["mode"])
    except (KeyError, TypeError):
        requested_mode = None

    if requested_mode is None:
        return invalid_mode_response()

    with state_lock:
        if ai_thinking:
            return ai_busy_response()
        set_current_mode(requested_mode)
        game.reset()
        return state_response()


@router.post("/difficulty")
def change_difficulty(payload: dict = Body(...)):
    try:
        requested_difficulty = validate_difficulty(payload["difficulty"])
    except (KeyError, TypeError):
        requested_difficulty = None

    if requested_difficulty is None:
        return invalid_difficulty_response()

    with state_lock:
        if ai_thinking:
            return ai_busy_response()
        set_current_difficulty(requested_difficulty)
        game.reset()
        return state_response()
