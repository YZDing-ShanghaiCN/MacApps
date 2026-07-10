from __future__ import annotations

import random

from gomoku.core.board import Board
from gomoku.core.enums import Player
from gomoku.core.rules import get_valid_moves


DIRECTIONS = (
    (0, 1),
    (1, 0),
    (1, 1),
    (1, -1),
)
RING_OFFSETS = (
    (-1, -1),
    (-1, 0),
    (-1, 1),
    (0, -1),
    (0, 1),
    (1, -1),
    (1, 0),
    (1, 1),
)


class RandomAI:
    """First-stage AI placeholder that chooses a random legal move."""

    def choose_move(self, board: Board) -> tuple[int, int] | None:
        moves = get_valid_moves(board)
        if not moves:
            return None
        return random.choice(moves)


class SimpleAI:
    """Deterministic rule-based AI.

    The AI follows a fixed first-match decision table. It does not use a
    value function, learning, random choices, or multi-move search.
    """

    def __init__(self, player: Player | int = Player.WHITE) -> None:
        self.player = Player(player)

    def choose_move(
        self,
        board: Board,
        player: Player | int | None = None,
        last_opponent_move: tuple[int, int] | None = None,
    ) -> tuple[int, int] | None:
        valid_moves = get_valid_moves(board)
        if not valid_moves:
            return None

        try:
            ai_player = self.player if player is None else Player(player)
        except ValueError:
            return valid_moves[0]

        opponent = ai_player.opponent
        if opponent == Player.EMPTY:
            return valid_moves[0]

        # The order below is the complete fixed policy. A later rule never
        # overrides an earlier matching rule.
        move = self._find_completion_move(board, ai_player, 5)
        if move is not None:
            return move

        move = self._find_completion_move(board, opponent, 5)
        if move is not None:
            return move

        move = self._find_completion_move(board, ai_player, 4)
        if move is not None:
            return move

        move = self._find_completion_move(board, opponent, 4)
        if move is not None:
            return move

        if self._is_valid_opponent_move(board, opponent, last_opponent_move):
            row, col = last_opponent_move
            if self._is_isolated_move(board, row, col, opponent):
                move = self._move_in_ring(board, row, col)
                if move is not None:
                    return move

        move = self._find_completion_move(board, opponent, 3)
        if move is not None:
            return move

        return self._fixed_fallback_move(board, valid_moves)

    def _is_valid_opponent_move(
        self,
        board: Board,
        opponent: Player,
        move: object,
    ) -> bool:
        if move is None:
            return False

        try:
            row, col = move
        except (TypeError, ValueError):
            return False

        if not isinstance(row, int) or not isinstance(col, int):
            return False

        return board.is_inside(row, col) and board.grid[row][col] == int(opponent)

    def _find_completion_move(
        self,
        board: Board,
        player: Player,
        line_length: int,
    ) -> tuple[int, int] | None:
        """Find the first direct line completion in fixed scan order."""

        if line_length <= 1:
            return None

        for dr, dc in DIRECTIONS:
            for row in range(board.size):
                for col in range(board.size):
                    cells = self._window_cells(board, row, col, dr, dc, line_length)
                    if cells is None:
                        continue

                    values = [board.grid[current_row][current_col] for current_row, current_col in cells]
                    if values.count(int(player)) != line_length - 1:
                        continue
                    if values.count(int(Player.EMPTY)) != 1:
                        continue

                    return cells[values.index(int(Player.EMPTY))]

        return None

    def _window_cells(
        self,
        board: Board,
        row: int,
        col: int,
        dr: int,
        dc: int,
        length: int,
    ) -> list[tuple[int, int]] | None:
        end_row = row + (length - 1) * dr
        end_col = col + (length - 1) * dc
        if not board.is_inside(end_row, end_col):
            return None

        return [
            (row + offset * dr, col + offset * dc)
            for offset in range(length)
        ]

    def _is_isolated_move(
        self,
        board: Board,
        row: int,
        col: int,
        player: Player,
    ) -> bool:
        for dr, dc in DIRECTIONS:
            for sign in (-1, 1):
                neighbor_row = row + sign * dr
                neighbor_col = col + sign * dc
                if (
                    board.is_inside(neighbor_row, neighbor_col)
                    and board.grid[neighbor_row][neighbor_col] == int(player)
                ):
                    return False

        return True

    def _move_in_ring(
        self,
        board: Board,
        row: int,
        col: int,
    ) -> tuple[int, int] | None:
        for row_offset, col_offset in RING_OFFSETS:
            candidate = (row + row_offset, col + col_offset)
            if board.is_empty(*candidate):
                return candidate

        return None

    def _fixed_fallback_move(
        self,
        board: Board,
        valid_moves: list[tuple[int, int]],
    ) -> tuple[int, int]:
        """Use a fixed center-out coordinate order without scoring."""

        center = board.size // 2
        for distance in range(board.size):
            for row in range(board.size):
                for col in range(board.size):
                    if max(abs(row - center), abs(col - center)) != distance:
                        continue
                    if board.is_empty(row, col):
                        return row, col

        return valid_moves[0]
