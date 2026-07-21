from __future__ import annotations

import random

from gomoku.core.board import Board
from gomoku.core.enums import Player
from gomoku.core.rules import check_win, get_valid_moves


DIRECTIONS = (
    (0, 1),
    (1, 0),
    (1, 1),
    (1, -1),
)

NEIGHBOR_DIRECTIONS = (
    (0, -1),
    (0, 1),
    (-1, 0),
    (1, 0),
    (-1, -1),
    (-1, 1),
    (1, -1),
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
    """Rule-based AI with a fixed priority table for continuous lines.

    Immediate wins and losses are handled for every five-in-a-row shape,
    including gapped fours. The remaining easy-difficulty strategy first
    extends its own continuous lines, then blocks the opponent's lines of the
    same length. Only equivalent blocking endpoints are random. If no
    continuous line of length two or greater can be extended, the AI grows an
    isolated own stone and then blocks an isolated opponent stone.
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

        own_wins = self._immediate_winning_moves(board, ai_player, valid_moves)
        if own_wins:
            return own_wins[0]
        opponent_wins = self._immediate_winning_moves(
            board,
            opponent,
            valid_moves,
        )
        if opponent_wins:
            return opponent_wins[0]

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

    def _immediate_winning_moves(
        self,
        board: Board,
        player: Player,
        valid_moves: list[tuple[int, int]],
    ) -> list[tuple[int, int]]:
        wins: list[tuple[int, int]] = []
        for row, col in valid_moves:
            board.grid[row][col] = int(player)
            try:
                if check_win(board, row, col, player):
                    wins.append((row, col))
            finally:
                board.grid[row][col] = int(Player.EMPTY)
        center = (board.size - 1) / 2
        return sorted(
            wins,
            key=lambda move: (
                max(abs(move[0] - center), abs(move[1] - center)),
                move[0],
                move[1],
            ),
        )

    def _find_isolated_stone_neighbor(
        self,
        board: Board,
        player: Player,
    ) -> tuple[int, int] | None:
        """Find the first legal square around an isolated stone.

        An isolated stone has no friendly stone in any of its eight adjacent
        squares. Nearby squares are ordered by their distance to the board
        center, then by horizontal, vertical, and diagonal directions. This
        keeps the low-priority strategy deterministic rather than selecting a
        random move elsewhere on the board.
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

                for row_offset, col_offset in self._ordered_neighbor_directions(
                    board,
                    row,
                    col,
                ):
                    candidate_row = row + row_offset
                    candidate_col = col + col_offset
                    if board.is_empty(candidate_row, candidate_col):
                        return candidate_row, candidate_col

        return None

    def _ordered_neighbor_directions(
        self,
        board: Board,
        row: int,
        col: int,
    ) -> tuple[tuple[int, int], ...]:
        center = (board.size - 1) / 2
        ordered_directions = sorted(
            enumerate(NEIGHBOR_DIRECTIONS),
            key=lambda item: (
                (row + item[1][0] - center) ** 2
                + (col + item[1][1] - center) ** 2,
                item[0],
            ),
        )
        return tuple(direction for _index, direction in ordered_directions)

    def _find_extension_move(
        self,
        board: Board,
        player: Player,
        line_length: int,
        *,
        randomize_endpoint: bool = False,
    ) -> tuple[int, int] | None:
        """Find a legal endpoint of the best matching maximal line.

        A line is considered only when it consists of exactly ``line_length``
        adjacent stones. This deliberately excludes gapped shapes such as
        ``XX_X`` and longer lines. A line with no empty endpoint is dead and
        cannot match this rule. Among matching lines, a line with two legal
        endpoints takes precedence over a line with only one legal endpoint.
        A move that is an endpoint for multiple matching lines takes
        precedence within the same endpoint category.
        """

        if line_length < 2:
            return None

        candidate_scores: dict[tuple[int, int], tuple[int, int]] = {}
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

                    for endpoint in endpoints:
                        best_endpoint_count, matching_line_count = (
                            candidate_scores.get(endpoint, (0, 0))
                        )
                        candidate_scores[endpoint] = (
                            max(best_endpoint_count, len(endpoints)),
                            matching_line_count + 1,
                        )

        if not candidate_scores:
            return None

        best_endpoint_count = max(score[0] for score in candidate_scores.values())
        best_line_count = max(
            score[1]
            for score in candidate_scores.values()
            if score[0] == best_endpoint_count
        )
        best_moves = [
            move
            for move, score in candidate_scores.items()
            if score == (best_endpoint_count, best_line_count)
        ]

        if randomize_endpoint:
            return random.choice(best_moves)
        return best_moves[0]
