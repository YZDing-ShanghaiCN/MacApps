from __future__ import annotations

from gomoku.core.game import GomokuGame


def game_to_response(game: GomokuGame) -> dict:
    """Return a JSON-friendly representation for future web APIs."""

    return game.get_state()
