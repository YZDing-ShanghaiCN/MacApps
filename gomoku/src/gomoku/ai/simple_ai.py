from __future__ import annotations

import random

from gomoku.core.board import Board
from gomoku.core.rules import get_valid_moves


class RandomAI:
    """First-stage AI placeholder that chooses a random legal move."""

    def choose_move(self, board: Board) -> tuple[int, int] | None:
        moves = get_valid_moves(board)
        if not moves:
            return None
        return random.choice(moves)
