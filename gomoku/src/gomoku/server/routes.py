from __future__ import annotations

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from gomoku import config
from gomoku.adapters.web_adapter import serialize_game_state
from gomoku.ai.simple_ai import SimpleAI
from gomoku.core.enums import Player
from gomoku.core.exceptions import GameOverError, InvalidMoveError
from gomoku.core.game import GomokuGame


router = APIRouter(prefix="/api")
game = GomokuGame()
current_mode = config.DEFAULT_MODE
AI_PLAYER = Player.WHITE
ai = SimpleAI(AI_PLAYER)


def active_ai_player() -> Player | None:
    if current_mode == config.MODE_VS_AI:
        return AI_PLAYER
    return None


def state_response() -> dict:
    return serialize_game_state(
        game,
        mode=current_mode,
        ai_player=active_ai_player(),
    )


def validate_mode(mode: object) -> str | None:
    if isinstance(mode, str) and mode in config.VALID_MODES:
        return mode
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


def set_current_mode(mode: str) -> None:
    global current_mode
    current_mode = mode


def maybe_play_ai_move(last_opponent_move: tuple[int, int]) -> None:
    if current_mode != config.MODE_VS_AI:
        return

    if game.game_over or game.current_player != AI_PLAYER:
        return

    ai_move = ai.choose_move(
        game.board,
        last_opponent_move=last_opponent_move,
    )
    if ai_move is not None:
        game.make_move(*ai_move)


def undo_for_current_mode() -> None:
    if current_mode == config.MODE_VS_AI:
        if game.undo() and game.current_player == AI_PLAYER:
            game.undo()
        return

    game.undo()


@router.get("/state")
def get_state() -> dict:
    return state_response()


@router.post("/move")
def make_move(payload: dict = Body(...)):
    try:
        row = int(payload["row"])
        col = int(payload["col"])
        game.make_move(row, col)
        maybe_play_ai_move((row, col))
    except (KeyError, TypeError, ValueError):
        return JSONResponse(
            status_code=400,
            content={"error": "Move request must include integer row and col."},
        )
    except InvalidMoveError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except GameOverError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})

    return state_response()


@router.post("/reset")
def reset_game(payload: dict | None = Body(default=None)):
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

    game.reset()
    return state_response()


@router.post("/start")
def start_game() -> dict:
    game.start_timer()
    return state_response()


@router.post("/undo")
def undo_move() -> dict:
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

    set_current_mode(requested_mode)
    game.reset()
    return state_response()
