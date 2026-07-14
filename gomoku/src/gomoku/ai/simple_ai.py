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

NEIGHBOR_DIRECTIONS = tuple(
    (row_offset, col_offset)
    for row_offset in (-1, 0, 1)
    for col_offset in (-1, 0, 1)
    if (row_offset, col_offset) != (0, 0)
)


class RandomAI:
    """First-stage AI placeholder that chooses a random legal move."""

    def choose_move(self, board: Board) -> tuple[int, int] | None:
        moves = get_valid_moves(board)
        if not moves:
            return None
        return random.choice(moves)


class SimpleAI:
    """Rule-based AI with a fixed priority table for continuous lines.

    The AI first extends its own continuous lines, then blocks the opponent's
    lines of the same length. Only the blocking endpoint is random. If no
    continuous line of length two or greater can be extended, the AI first
    grows an isolated own stone and then blocks an isolated opponent stone.
    It chooses randomly only when no such nearby move exists.
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

        # A higher line length always wins. For a given length, extending our
        # own line takes precedence over blocking the opponent's line.
        # ``last_opponent_move`` remains part of the public API for callers,
        # but the complete board state now determines every strategy choice.
        for line_length in (4, 3, 2):
            move = self._find_extension_move(board, ai_player, line_length)
            if move is not None:
                return move

            move = self._find_extension_move(
                board,
                opponent,
                line_length,
                randomize_endpoint=True,
            )
            if move is not None:
                return move

        move = self._find_isolated_stone_neighbor(board, ai_player)
        if move is not None:
            return move

        move = self._find_isolated_stone_neighbor(board, opponent)
        if move is not None:
            return move

        return random.choice(valid_moves)

    def _find_isolated_stone_neighbor(
        self,
        board: Board,
        player: Player,
    ) -> tuple[int, int] | None:
        """Find the first legal square around an isolated stone.

        An isolated stone has no friendly stone in any of its eight adjacent
        squares. Scanning the surrounding ring in a fixed order keeps this
        low-priority strategy deterministic rather than selecting a random
        move elsewhere on the board.
        """

        for row in range(board.size):
            for col in range(board.size):
                if board.grid[row][col] != int(player):
                    continue
                if any(
                    board.is_inside(row + row_offset, col + col_offset)
                    and board.grid[row + row_offset][col + col_offset]
                    == int(player)
                    for row_offset, col_offset in NEIGHBOR_DIRECTIONS
                ):
                    continue

                for row_offset, col_offset in NEIGHBOR_DIRECTIONS:
                    candidate_row = row + row_offset
                    candidate_col = col + col_offset
                    if board.is_empty(candidate_row, candidate_col):
                        return candidate_row, candidate_col

        return None

    def _find_extension_move(
        self,
        board: Board,
        player: Player,
        line_length: int,
        *,
        randomize_endpoint: bool = False,
    ) -> tuple[int, int] | None:
        """Find a legal endpoint of the first matching maximal line.

        A line is considered only when it consists of exactly ``line_length``
        adjacent stones. This deliberately excludes gapped shapes such as
        ``XX_X`` and longer lines. A line with no empty endpoint is dead and
        cannot match this rule.
        """

        if line_length < 2:
            return None

        for dr, dc in DIRECTIONS:
            for row in range(board.size):
                for col in range(board.size):
                    if board.grid[row][col] != int(player):
                        continue

                    before_row = row - dr
                    before_col = col - dc
                    if (
                        board.is_inside(before_row, before_col)
                        and board.grid[before_row][before_col] == int(player)
                    ):
                        continue

                    end_row = row
                    end_col = col
                    current_length = 1
                    while True:
                        next_row = end_row + dr
                        next_col = end_col + dc
                        if (
                            not board.is_inside(next_row, next_col)
                            or board.grid[next_row][next_col] != int(player)
                        ):
                            break
                        end_row = next_row
                        end_col = next_col
                        current_length += 1

                    if current_length != line_length:
                        continue

                    endpoints = [
                        (candidate_row, candidate_col)
                        for candidate_row, candidate_col in (
                            (before_row, before_col),
                            (end_row + dr, end_col + dc),
                        )
                        if board.is_empty(candidate_row, candidate_col)
                    ]
                    if not endpoints:
                        continue

                    if randomize_endpoint:
                        return random.choice(endpoints)
                    return endpoints[0]

        return None
