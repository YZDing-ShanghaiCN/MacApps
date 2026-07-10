from __future__ import annotations

import random

from gomoku.core.board import Board
from gomoku.core.enums import Player
from gomoku.core.rules import get_valid_moves


SEARCH_RADIUS = 4
BLOCK_PRIORITIES = (4, 3, 2)
DIRECTIONS = (
    (0, 1),
    (1, 0),
    (1, 1),
    (1, -1),
)


class RandomAI:
    """First-stage AI placeholder that chooses a random legal move."""

    def choose_move(self, board: Board) -> tuple[int, int] | None:
        moves = get_valid_moves(board)
        if not moves:
            return None
        return random.choice(moves)


class SimpleAI:
    """Basic defensive AI that blocks nearby opponent lines."""

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
            return random.choice(valid_moves)

        opponent = ai_player.opponent
        if opponent == Player.EMPTY:
            return random.choice(valid_moves)

        if not self._is_valid_opponent_move(board, opponent, last_opponent_move):
            return random.choice(valid_moves)

        row, col = last_opponent_move
        scoped_moves = self._valid_moves_near(board, row, col)
        if not scoped_moves:
            return random.choice(valid_moves)

        for priority in BLOCK_PRIORITIES:
            blockers = self._blockers_for_priority(board, row, col, opponent, priority)
            if blockers:
                return random.choice(blockers)

        return random.choice(scoped_moves)

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

    def _valid_moves_near(self, board: Board, row: int, col: int) -> list[tuple[int, int]]:
        row_start = max(0, row - SEARCH_RADIUS)
        row_end = min(board.size - 1, row + SEARCH_RADIUS)
        col_start = max(0, col - SEARCH_RADIUS)
        col_end = min(board.size - 1, col + SEARCH_RADIUS)

        return [
            (current_row, current_col)
            for current_row in range(row_start, row_end + 1)
            for current_col in range(col_start, col_end + 1)
            if board.is_empty(current_row, current_col)
        ]

    def _blockers_for_priority(
        self,
        board: Board,
        row: int,
        col: int,
        opponent: Player,
        priority: int,
    ) -> list[tuple[int, int]]:
        blockers: list[tuple[int, int]] = []
        for dr, dc in DIRECTIONS:
            total, ends = self._line_info(board, row, col, dr, dc, opponent)
            if total >= priority:
                blockers.extend(ends)

        return list(dict.fromkeys(blockers))

    def _line_info(
        self,
        board: Board,
        row: int,
        col: int,
        dr: int,
        dc: int,
        opponent: Player,
    ) -> tuple[int, list[tuple[int, int]]]:
        backward_count, backward_end = self._scan_direction(
            board,
            row,
            col,
            -dr,
            -dc,
            opponent,
        )
        forward_count, forward_end = self._scan_direction(
            board,
            row,
            col,
            dr,
            dc,
            opponent,
        )

        ends = [
            move
            for move in (backward_end, forward_end)
            if move is not None
            and abs(move[0] - row) <= SEARCH_RADIUS
            and abs(move[1] - col) <= SEARCH_RADIUS
        ]
        return 1 + backward_count + forward_count, ends

    def _scan_direction(
        self,
        board: Board,
        row: int,
        col: int,
        dr: int,
        dc: int,
        opponent: Player,
    ) -> tuple[int, tuple[int, int] | None]:
        count = 0
        current_row = row + dr
        current_col = col + dc

        while (
            board.is_inside(current_row, current_col)
            and board.grid[current_row][current_col] == int(opponent)
        ):
            count += 1
            current_row += dr
            current_col += dc

        if board.is_empty(current_row, current_col):
            return count, (current_row, current_col)

        return count, None
