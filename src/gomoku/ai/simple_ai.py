from __future__ import annotations

import random
from dataclasses import asdict, dataclass

from gomoku.ai.simple_ai_config import (
    DEFAULT_SIMPLE_AI_CONFIG,
    TIE_BREAK_VARIED,
    SimpleAIConfig,
)
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


Move = tuple[int, int]


@dataclass(frozen=True)
class SimpleCandidateScore:
    move: Move
    score: int


@dataclass(frozen=True)
class SimpleDecision:
    reason: str = "not_searched"
    selected_move: Move | None = None
    candidates: tuple[SimpleCandidateScore, ...] = ()


class RandomAI:
    """First-stage AI placeholder that chooses a random legal move."""

    def __init__(self, seed: int | None = None) -> None:
        self.rng = random.Random(seed)

    def choose_move(self, board: Board) -> tuple[int, int] | None:
        moves = get_valid_moves(board)
        if not moves:
            return None
        return self.rng.choice(moves)


class SimpleAI:
    """Rule-based AI with a fixed priority table for continuous lines.

    Immediate wins and losses are handled for every five-in-a-row shape,
    including gapped fours. The remaining easy-difficulty strategy first
    extends its own continuous lines, then blocks the opponent's lines of the
    same length. Only equivalent blocking endpoints are random. If no
    continuous line of length two or greater can be extended, the AI grows an
    isolated own stone and then blocks an isolated opponent stone.
    """

    def __init__(
        self,
        player: Player | int = Player.WHITE,
        *,
        config: SimpleAIConfig = DEFAULT_SIMPLE_AI_CONFIG,
    ) -> None:
        self.player = Player(player)
        self.config = config
        self.rng = random.Random(config.random_seed)
        self.random_choices = 0
        self.last_decision = SimpleDecision()

    def debug_state(self) -> dict:
        """Return enough state to reproduce the next varied tie break."""

        return {
            "config": asdict(self.config),
            "random_seed": self.config.random_seed,
            "random_choices": self.random_choices,
            "decision": asdict(self.last_decision),
        }

    def choose_move(
        self,
        board: Board,
        player: Player | int | None = None,
        last_opponent_move: tuple[int, int] | None = None,
    ) -> tuple[int, int] | None:
        valid_moves = get_valid_moves(board)
        if not valid_moves:
            self.last_decision = SimpleDecision(reason="no_legal_move")
            return None

        try:
            ai_player = self.player if player is None else Player(player)
        except ValueError:
            return self._finish("invalid_player_fallback", valid_moves[:1], 0)

        opponent = ai_player.opponent
        if opponent == Player.EMPTY:
            return self._finish("invalid_opponent_fallback", valid_moves[:1], 0)

        own_wins = self._immediate_winning_moves(board, ai_player, valid_moves)
        if own_wins:
            return self._finish("immediate_win", own_wins, 100_000)
        opponent_wins = self._immediate_winning_moves(
            board,
            opponent,
            valid_moves,
        )
        if opponent_wins:
            return self._finish("immediate_block", opponent_wins, 90_000)

        # A higher line length always wins. For a given length, extending our
        # own line takes precedence over blocking the opponent's line.
        # ``last_opponent_move`` remains part of the public API for callers,
        # but the complete board state now determines every strategy choice.
        for line_length in (4, 3, 2):
            own_extensions = self._find_extension_moves(
                board,
                ai_player,
                line_length,
            )
            if own_extensions:
                return self._finish(
                    f"extend_own_{line_length}",
                    own_extensions,
                    50_000 + line_length * 1_000,
                )

            opponent_extensions = self._find_extension_moves(
                board,
                opponent,
                line_length,
            )
            if opponent_extensions:
                return self._finish(
                    f"block_opponent_{line_length}",
                    opponent_extensions,
                    40_000 + line_length * 1_000,
                    varied=True,
                )

        move = self._find_isolated_stone_neighbor(board, ai_player)
        if move is not None:
            return self._finish("grow_isolated_own_stone", [move], 20_000)

        move = self._find_isolated_stone_neighbor(board, opponent)
        if move is not None:
            return self._finish("block_isolated_opponent_stone", [move], 10_000)

        return self._fallback_move(board, ai_player, valid_moves)

    def _finish(
        self,
        reason: str,
        candidates: list[Move],
        score: int,
        *,
        varied: bool = False,
    ) -> Move:
        ordered = sorted(candidates)
        if varied and self.config.tie_break_mode == TIE_BREAK_VARIED:
            selected = self.rng.choice(ordered)
            self.random_choices += 1
        else:
            selected = ordered[0]
        self.last_decision = SimpleDecision(
            reason=reason,
            selected_move=selected,
            candidates=tuple(
                SimpleCandidateScore(move=move, score=score)
                for move in ordered[:3]
            ),
        )
        return selected

    def _fallback_move(
        self,
        board: Board,
        ai_player: Player,
        valid_moves: list[Move],
    ) -> Move:
        occupied = [
            (row, col)
            for row in range(board.size)
            for col in range(board.size)
            if board.grid[row][col] != int(Player.EMPTY)
        ]
        if not occupied:
            center = board.size // 2
            return self._finish("empty_board_center", [(center, center)], 1_000)

        radius = self.config.fallback_radius
        nearby = [
            move
            for move in valid_moves
            if any(
                max(abs(move[0] - row), abs(move[1] - col)) <= radius
                for row, col in occupied
            )
        ]
        candidates = nearby or valid_moves
        center = (board.size - 1) / 2
        scored: list[SimpleCandidateScore] = []
        for move in candidates:
            own_neighbors = 0
            opponent_neighbors = 0
            for dr, dc in NEIGHBOR_DIRECTIONS:
                row = move[0] + dr
                col = move[1] + dc
                if not board.is_inside(row, col):
                    continue
                value = board.grid[row][col]
                if value == int(ai_player):
                    own_neighbors += 1
                elif value == int(ai_player.opponent):
                    opponent_neighbors += 1
            center_distance = int(
                max(abs(move[0] - center), abs(move[1] - center))
            )
            score = (
                own_neighbors * self.config.fallback_own_neighbor_weight
                + opponent_neighbors * self.config.fallback_opponent_neighbor_weight
                - center_distance * self.config.fallback_center_weight
            )
            scored.append(SimpleCandidateScore(move, score))

        scored.sort(key=lambda item: (-item.score, item.move[0], item.move[1]))
        best_score = scored[0].score
        best_moves = [item.move for item in scored if item.score == best_score]
        if self.config.tie_break_mode == TIE_BREAK_VARIED:
            selected = self.rng.choice(best_moves)
            self.random_choices += 1
        else:
            selected = best_moves[0]
        self.last_decision = SimpleDecision(
            reason="nearby_fallback" if nearby else "legal_fallback",
            selected_move=selected,
            candidates=tuple(scored[:3]),
        )
        return selected

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

        moves = self._find_extension_moves(board, player, line_length)
        if not moves:
            return None
        if randomize_endpoint and self.config.tie_break_mode == TIE_BREAK_VARIED:
            self.random_choices += 1
            return self.rng.choice(moves)
        return moves[0]

    def _find_extension_moves(
        self,
        board: Board,
        player: Player,
        line_length: int,
    ) -> list[Move]:
        if line_length < 2:
            return []

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
            return []

        best_endpoint_count = max(score[0] for score in candidate_scores.values())
        best_line_count = max(
            score[1]
            for score in candidate_scores.values()
            if score[0] == best_endpoint_count
        )
        return sorted(
            [
            move
            for move, score in candidate_scores.items()
            if score == (best_endpoint_count, best_line_count)
            ]
        )
