"""Deterministic iterative-deepening Negamax AI for normal difficulty."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from gomoku.ai.candidate_generator import CandidateGenerator
from gomoku.ai.evaluator import StaticEvaluator
from gomoku.ai.normal_ai_config import (
    DEFAULT_NORMAL_AI_CONFIG,
    NormalAIConfig,
)
from gomoku.ai.pattern_matcher import PatternMatcher
from gomoku.ai.search_position import SearchPosition
from gomoku.ai.transposition_table import (
    BoundType,
    TranspositionEntry,
    TranspositionTable,
)
from gomoku.ai.zobrist import ZobristTable
from gomoku.core.board import Board
from gomoku.core.enums import Player
from gomoku.core.rules import check_win, get_valid_moves


Move = tuple[int, int]


class SearchTimeout(RuntimeError):
    """Internal control-flow exception for a cooperative hard deadline."""


@dataclass(frozen=True)
class SearchStats:
    completed_depth: int = 0
    nodes: int = 0
    tt_hits: int = 0
    timed_out: bool = False
    elapsed_ms: float = 0.0


class NormalAI:
    def __init__(
        self,
        player: Player | int = Player.WHITE,
        *,
        config: NormalAIConfig = DEFAULT_NORMAL_AI_CONFIG,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.player = Player(player)
        if self.player == Player.EMPTY:
            raise ValueError("NormalAI player cannot be empty.")
        self.config = config
        self.clock = clock
        self.matcher = PatternMatcher()
        self.evaluator = StaticEvaluator(config, self.matcher)
        self.candidates = CandidateGenerator(config, self.matcher)
        self.transposition_table = TranspositionTable(
            config.transposition_capacity
        )
        self._zobrist_tables: dict[int, ZobristTable] = {}
        self._deadline = 0.0
        self._started_at = 0.0
        self._nodes = 0
        self._tt_hits = 0
        self._perspective = self.player
        self.last_search_stats = SearchStats()

    def choose_move(
        self,
        board: Board,
        player: Player | int | None = None,
        last_opponent_move: Move | None = None,
    ) -> Move | None:
        del last_opponent_move  # The complete board is the source of truth.
        valid_moves = get_valid_moves(board)
        if not valid_moves:
            self.last_search_stats = SearchStats()
            return None

        try:
            perspective = self.player if player is None else Player(player)
        except ValueError:
            perspective = self.player
        if perspective == Player.EMPTY:
            perspective = self.player
        if perspective != self._perspective:
            self.transposition_table.clear()
            self._perspective = perspective

        fallback = min(
            valid_moves,
            key=lambda move: (
                self._center_distance(board.size, move),
                move[0],
                move[1],
            ),
        )
        self._started_at = self.clock()
        usable_ms = max(
            0,
            self.config.time_limit_ms - self.config.time_safety_margin_ms,
        )
        self._deadline = self._started_at + usable_ms / 1000
        self._nodes = 0
        self._tt_hits = 0
        self.transposition_table.new_generation()

        zobrist = self._zobrist_for_size(board.size)
        position = SearchPosition.from_board(board, perspective, zobrist)
        best_move = fallback
        completed_depth = 0
        timed_out = False

        try:
            own_wins = self.candidates.immediate_wins(
                position,
                perspective,
                self._force_timeout_check,
            )
            if own_wins:
                return self._finish(own_wins[0], completed_depth, False)

            opponent_wins = self.candidates.immediate_wins(
                position,
                perspective.opponent,
                self._force_timeout_check,
            )
            if opponent_wins:
                return self._finish(opponent_wins[0], completed_depth, False)

            for depth in range(1, self.config.max_depth + 1):
                self._force_timeout_check()
                _score, depth_move = self._search_root(position, depth)
                if depth_move is not None:
                    best_move = depth_move
                completed_depth = depth
        except SearchTimeout:
            timed_out = True

        return self._finish(best_move, completed_depth, timed_out)

    def _search_root(
        self,
        position: SearchPosition,
        depth: int,
    ) -> tuple[int, Move | None]:
        alpha = -self.config.infinity_score
        beta = self.config.infinity_score
        original_alpha = alpha
        original_beta = beta
        entry = self.transposition_table.probe(position.hash_key)
        tt_move = entry.best_move if entry is not None else None
        moves = self.candidates.generate(
            position,
            root=True,
            tt_move=tt_move,
            timeout_check=self._force_timeout_check,
        )
        best_score = -self.config.infinity_score
        best_move: Move | None = None

        for move in moves:
            self._force_timeout_check()
            position.make_move(*move)
            try:
                score = -self._negamax(
                    position,
                    depth - 1,
                    -beta,
                    -alpha,
                    ply=1,
                    color=-1,
                    extension_depth=self.config.threat_extension_depth,
                )
            finally:
                position.undo_move()

            if score > best_score:
                best_score = score
                best_move = move
            if self.config.enable_alpha_beta and score > alpha:
                alpha = score
            if self.config.enable_alpha_beta and alpha >= beta:
                break

        if best_move is not None:
            bound = self._bound_type(best_score, original_alpha, original_beta)
            self.transposition_table.store(
                TranspositionEntry(
                    key=position.hash_key,
                    depth=depth,
                    score=self._score_to_tt(best_score, 0),
                    bound=bound,
                    best_move=best_move,
                    generation=self.transposition_table.generation,
                    extension_depth=self.config.threat_extension_depth,
                )
            )
        return best_score, best_move

    def _negamax(
        self,
        position: SearchPosition,
        depth: int,
        alpha: int,
        beta: int,
        *,
        ply: int,
        color: int,
        extension_depth: int,
    ) -> int:
        self._nodes += 1
        self._check_timeout()

        last_move = position.last_move
        if last_move is not None and check_win(
            position,
            last_move.row,
            last_move.col,
            last_move.player,
        ):
            return -self.config.mate_score + ply
        if position.empty_count == 0:
            return 0

        original_alpha = alpha
        original_beta = beta
        tt_move: Move | None = None
        entry = self.transposition_table.probe(position.hash_key)
        if entry is not None:
            tt_move = entry.best_move
            if (
                entry.depth >= max(depth, 0)
                and entry.extension_depth >= extension_depth
            ):
                self._tt_hits += 1
                tt_score = self._score_from_tt(entry.score, ply)
                if entry.bound == BoundType.EXACT:
                    return tt_score
                if self.config.enable_alpha_beta:
                    if entry.bound == BoundType.LOWER:
                        alpha = max(alpha, tt_score)
                    else:
                        beta = min(beta, tt_score)
                    if alpha >= beta:
                        return tt_score

        if depth <= 0:
            if extension_depth <= 0:
                return color * self.evaluator.evaluate(
                    position,
                    self._perspective,
                    self._force_timeout_check,
                )
            forcing_moves = self.candidates.generate(
                position,
                root=False,
                tt_move=tt_move,
                forcing_only=True,
                timeout_check=self._force_timeout_check,
            )
            if not forcing_moves:
                return color * self.evaluator.evaluate(
                    position,
                    self._perspective,
                    self._force_timeout_check,
                )
            moves = forcing_moves
            next_depth = 0
            next_extension = extension_depth - 1
        else:
            moves = self.candidates.generate(
                position,
                root=False,
                tt_move=tt_move,
                timeout_check=self._force_timeout_check,
            )
            next_depth = depth - 1
            next_extension = extension_depth

        if not moves:
            return color * self.evaluator.evaluate(
                position,
                self._perspective,
                self._force_timeout_check,
            )

        best_score = -self.config.infinity_score
        best_move: Move | None = None
        for move in moves:
            position.make_move(*move)
            try:
                score = -self._negamax(
                    position,
                    next_depth,
                    -beta,
                    -alpha,
                    ply=ply + 1,
                    color=-color,
                    extension_depth=next_extension,
                )
            finally:
                position.undo_move()

            if score > best_score:
                best_score = score
                best_move = move
            if self.config.enable_alpha_beta:
                alpha = max(alpha, score)
            if self.config.enable_alpha_beta and alpha >= beta:
                break

        if best_move is not None:
            bound = self._bound_type(best_score, original_alpha, original_beta)
            self.transposition_table.store(
                TranspositionEntry(
                    key=position.hash_key,
                    depth=max(depth, 0),
                    score=self._score_to_tt(best_score, ply),
                    bound=bound,
                    best_move=best_move,
                    generation=self.transposition_table.generation,
                    extension_depth=extension_depth,
                )
            )
        return best_score

    def _bound_type(self, score: int, original_alpha: int, beta: int) -> BoundType:
        if score <= original_alpha:
            return BoundType.UPPER
        if score >= beta:
            return BoundType.LOWER
        return BoundType.EXACT

    def _score_to_tt(self, score: int, ply: int) -> int:
        threshold = self.config.mate_score - self.config.board_size**2
        if score >= threshold:
            return score + ply
        if score <= -threshold:
            return score - ply
        return score

    def _score_from_tt(self, score: int, ply: int) -> int:
        threshold = self.config.mate_score - self.config.board_size**2
        if score >= threshold:
            return score - ply
        if score <= -threshold:
            return score + ply
        return score

    def _check_timeout(self) -> None:
        interval = max(1, self.config.timeout_check_interval_nodes)
        if self._nodes % interval == 0:
            self._force_timeout_check()

    def _force_timeout_check(self) -> None:
        if self.clock() >= self._deadline:
            raise SearchTimeout

    def _zobrist_for_size(self, size: int) -> ZobristTable:
        if size not in self._zobrist_tables:
            self._zobrist_tables[size] = ZobristTable(
                size,
                self.config.zobrist_seed ^ size,
            )
        return self._zobrist_tables[size]

    def _finish(
        self,
        move: Move,
        completed_depth: int,
        timed_out: bool,
    ) -> Move:
        elapsed_ms = max(0.0, (self.clock() - self._started_at) * 1000)
        self.last_search_stats = SearchStats(
            completed_depth=completed_depth,
            nodes=self._nodes,
            tt_hits=self._tt_hits,
            timed_out=timed_out,
            elapsed_ms=elapsed_ms,
        )
        return move

    def _center_distance(self, size: int, move: Move) -> float:
        center = (size - 1) / 2
        return max(abs(move[0] - center), abs(move[1] - center))
