from __future__ import annotations

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from gomoku.adapters.web_adapter import serialize_game_state
from gomoku.core.exceptions import GameOverError, InvalidMoveError
from gomoku.core.game import GomokuGame


router = APIRouter(prefix="/api")
game = GomokuGame()


@router.get("/state")
def get_state() -> dict:
    return serialize_game_state(game)


@router.post("/move")
def make_move(payload: dict = Body(...)):
    try:
        row = int(payload["row"])
        col = int(payload["col"])
        game.make_move(row, col)
    except (KeyError, TypeError, ValueError):
        return JSONResponse(
            status_code=400,
            content={"error": "Move request must include integer row and col."},
        )
    except InvalidMoveError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except GameOverError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})

    return serialize_game_state(game)


@router.post("/reset")
def reset_game() -> dict:
    game.reset()
    return serialize_game_state(game)


@router.post("/undo")
def undo_move() -> dict:
    game.undo()
    return serialize_game_state(game)
