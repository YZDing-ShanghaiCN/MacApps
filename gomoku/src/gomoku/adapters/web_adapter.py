from __future__ import annotations

from gomoku import config
from gomoku.core.enums import Player
from gomoku.core.game import GomokuGame


def player_name(player: Player | int | None) -> str | None:
    if player is None:
        return None

    player_value = Player(player)
    if player_value == Player.BLACK:
        return "Black"
    if player_value == Player.WHITE:
        return "White"
    return None


def serialize_last_move(game: GomokuGame) -> dict | None:
    if not game.move_history:
        return None

    row, col, player = game.move_history[-1]
    return {
        "row": row,
        "col": col,
        "player": int(player),
    }


def serialize_game_state(
    game: GomokuGame,
    mode: str = config.DEFAULT_MODE,
    ai_player: Player | int | None = None,
) -> dict:
    """Return a JSON-friendly game state for the web API."""

    state = game.get_state()
    return {
        "board": state["board"],
        "size": state["size"],
        "current_player": state["current_player"],
        "current_player_name": player_name(game.current_player),
        "winner": state["winner"],
        "winner_name": player_name(game.winner),
        "game_over": state["game_over"],
        "winning_line": state["winning_line"],
        "timer_running": state["timer_running"],
        "time_spent": state["time_spent"],
        "move_count": len(game.move_history),
        "last_move": serialize_last_move(game),
        "mode": mode,
        "ai_player": int(ai_player) if ai_player is not None else None,
    }


def game_to_response(
    game: GomokuGame,
    mode: str = config.DEFAULT_MODE,
    ai_player: Player | int | None = None,
) -> dict:
    """Backward-compatible alias for older web API code."""

    return serialize_game_state(game, mode=mode, ai_player=ai_player)
