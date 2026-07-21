"""Deterministic iterative-deepening Negamax AI for normal difficulty."""

from __future__ import annotations

import time
import threading
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass

from gomoku.ai.candidate_generator import CandidateGenerator
from gomoku.ai.evaluator import StaticEvaluator
from gomoku.ai.normal_ai_config import (
    DEFAULT_NORMAL_AI_CONFIG,
    NormalAIConfig,
)
from gomoku.ai.pattern_matcher import PatternKind, PatternMatcher
from gomoku.ai.search_position import SearchPosition
from gomoku.ai.transposition_table import (
    BoundType,
    TranspositionEntry,
    TranspositionTable,
)
from gomoku.ai.zobrist import ZobristTable
from gomoku.ai.vcf_search import VCFSearch, VCFTimeout
from gomoku.core.board import Board
from gomoku.core.enums import Player
from gomoku.core.rules import check_win, get_valid_moves


Move = tuple[int, int]


class SearchTimeout(RuntimeError):
    """Internal control-flow exception for a cooperative hard deadline."""


@dataclass(frozen=True)
class DepthResult:
    depth: int
    score: int
    best_move: Move | None
    nodes: int
    elapsed_ms: float


@dataclass(frozen=True)
class RootMoveScore:
    move: Move
    score: int


@dataclass(frozen=True)
class SearchStats:
    completed_depth: int = 0
    nodes: int = 0
    tt_hits: int = 0
    timed_out: bool = False
    elapsed_ms: float = 0.0
    beta_cutoffs: int = 0
    tt_cutoffs: int = 0
    eval_cache_hits: int = 0
    quiescence_nodes: int = 0
    max_ply: int = 0
    tt_collisions: int = 0
    tt_replacements: int = 0
    vcf_found: bool = False
    vcf_nodes: int = 0
    defensive_vcf_detected: bool = False
    defensive_vcf_moves: tuple[Move, ...] = ()
    depth_results: tuple[DepthResult, ...] = ()
    root_moves: tuple[RootMoveScore, ...] = ()


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
        self.matcher = PatternMatcher(config.pattern_line_cache_capacity)
        self.evaluator = StaticEvaluator(config, self.matcher)
        self.candidates = CandidateGenerator(config, self.matcher)
        self.vcf_search = VCFSearch(config, self.candidates)
        self.transposition_table = TranspositionTable(
            config.transposition_capacity,
            config.transposition_bucket_size,
        )
        self._zobrist_tables: dict[int, ZobristTable] = {}
        self._deadline = 0.0
        self._started_at = 0.0
        self._nodes = 0
        self._tt_hits = 0
        self._tt_cutoffs = 0
        self._beta_cutoffs = 0
        self._eval_cache_hits = 0
        self._quiescence_nodes = 0
        self._max_ply = 0
        self._depth_results: list[DepthResult] = []
        self._latest_root_scores: list[RootMoveScore] = []
        self._completed_root_scores: list[RootMoveScore] = []
        self._history: dict[tuple[Player, Move], int] = {}
        self._killers: dict[int, list[Move]] = {}
        self._evaluation_cache: OrderedDict[tuple[int, Player], int] = OrderedDict()
        self._tt_collision_start = 0
        self._tt_replacement_start = 0
        self._vcf_found = False
        self._vcf_nodes = 0
        self._defensive_vcf_detected = False
        self._defensive_vcf_moves: tuple[Move, ...] = ()
        self._forced_root_moves: set[Move] | None = None
        self._vcf_deadline = 0.0
        self._cancel_event: threading.Event | None = None
        self._search_lock = threading.Lock()
        self._perspective = self.player
        self.last_search_stats = SearchStats()

    def choose_move(
        self,
        board: Board,
        player: Player | int | None = None,
        last_opponent_move: Move | None = None,
        cancel_event: threading.Event | None = None,
    ) -> Move | None:
        with self._search_lock:
            return self._choose_move(
                board,
                player,
                last_opponent_move,
                cancel_event,
            )

    def _choose_move(
        self,
        board: Board,
        player: Player | int | None,
        last_opponent_move: Move | None,
        cancel_event: threading.Event | None,
    ) -> Move | None:
        del last_opponent_move  # The complete board is the source of truth.
        self._cancel_event = cancel_event
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
            self._evaluation_cache.clear()
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
        self._tt_cutoffs = 0
        self._beta_cutoffs = 0
        self._eval_cache_hits = 0
        self._quiescence_nodes = 0
        self._max_ply = 0
        self._depth_results = []
        self._latest_root_scores = []
        self._completed_root_scores = []
        self._history.clear()
        self._killers.clear()
        self._tt_collision_start = self.transposition_table.collisions
        self._tt_replacement_start = self.transposition_table.replacements
        self._vcf_found = False
        self._vcf_nodes = 0
        self._defensive_vcf_detected = False
        self._defensive_vcf_moves = ()
        self._forced_root_moves = None
        self.transposition_table.new_generation()

        zobrist = self._zobrist_for_size(board.size)
        position = SearchPosition.from_board(
            board,
            perspective,
            zobrist,
            max_candidate_radius=max(1, self.config.candidate_radius),
        )
        self.evaluator.prepare(position)
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

            vcf_start_kinds = {
                PatternKind.OPEN_THREE,
                PatternKind.JUMP_THREE,
                PatternKind.CLOSED_THREE,
                PatternKind.CLOSED_FOUR,
            }
            own_patterns = self._position_patterns(position, perspective)
            opponent_patterns = self._position_patterns(
                position,
                perspective.opponent,
            )
            has_vcf_start = any(
                pattern.kind in vcf_start_kinds for pattern in own_patterns
            )
            if (
                self.config.enable_vcf
                and self.config.vcf_max_depth > 0
                and has_vcf_start
            ):
                vcf_budget = (
                    usable_ms
                    * max(0.0, min(1.0, self.config.vcf_time_fraction))
                    / 1000
                )
                self._vcf_deadline = min(
                    self._deadline,
                    self.clock() + vcf_budget,
                )
                try:
                    vcf_move = self.vcf_search.find_winning_move(
                        position,
                        perspective,
                        self._vcf_timeout_check,
                    )
                except VCFTimeout:
                    vcf_move = None
                self._vcf_nodes += self.vcf_search.nodes
                if vcf_move is not None:
                    self._vcf_found = True
                    return self._finish(vcf_move, completed_depth, False)

            opponent_has_vcf_start = any(
                pattern.kind in vcf_start_kinds
                for pattern in opponent_patterns
            )
            if (
                self.config.enable_defensive_vcf
                and self.config.vcf_max_depth > 0
                and opponent_has_vcf_start
            ):
                defensive_budget = (
                    usable_ms
                    * max(
                        0.0,
                        min(1.0, self.config.defensive_vcf_time_fraction),
                    )
                    / 1000
                )
                self._vcf_deadline = min(
                    self._deadline,
                    self.clock() + defensive_budget,
                )
                try:
                    threat_found, defensive_moves = (
                        self.vcf_search.find_defensive_moves(
                            position,
                            perspective,
                            self._vcf_timeout_check,
                        )
                    )
                except VCFTimeout:
                    threat_found, defensive_moves = False, ()
                self._vcf_nodes += self.vcf_search.nodes
                if threat_found:
                    self._defensive_vcf_detected = True
                    self._defensive_vcf_moves = defensive_moves
                    if defensive_moves:
                        fallback = defensive_moves[0]
                        self._forced_root_moves = set(defensive_moves)

            previous_score: int | None = None
            for depth in range(1, self.config.max_depth + 1):
                self._force_timeout_check()
                nodes_before = self._nodes
                if previous_score is None or self.config.aspiration_window <= 0:
                    score, depth_move = self._search_root(position, depth)
                else:
                    window = self.config.aspiration_window
                    low = max(-self.config.infinity_score, previous_score - window)
                    high = min(self.config.infinity_score, previous_score + window)
                    score, depth_move = self._search_root(
                        position,
                        depth,
                        alpha=low,
                        beta=high,
                    )
                    if score <= low or score >= high:
                        score, depth_move = self._search_root(position, depth)
                if depth_move is not None:
                    best_move = depth_move
                completed_depth = depth
                previous_score = score
                self._completed_root_scores = list(self._latest_root_scores)
                self._depth_results.append(
                    DepthResult(
                        depth=depth,
                        score=score,
                        best_move=depth_move,
                        nodes=self._nodes - nodes_before,
                        elapsed_ms=max(
                            0.0,
                            (self.clock() - self._started_at) * 1000,
                        ),
                    )
                )
        except SearchTimeout:
            timed_out = True

        return self._finish(best_move, completed_depth, timed_out)

    def _search_root(
        self,
        position: SearchPosition,
        depth: int,
        alpha: int | None = None,
        beta: int | None = None,
    ) -> tuple[int, Move | None]:
        alpha = -self.config.infinity_score if alpha is None else alpha
        beta = self.config.infinity_score if beta is None else beta
        original_alpha = alpha
        original_beta = beta
        entry = self.transposition_table.probe(position.hash_key)
        tt_move = entry.best_move if entry is not None else None
        moves = self.candidates.generate(
            position,
            root=True,
            tt_move=tt_move,
            timeout_check=self._force_timeout_check,
            ordering_bonus=lambda move: self._ordering_bonus(
                position.current_player,
                move,
                0,
            ),
        )
        if self._forced_root_moves is not None:
            moves = [move for move in moves if move in self._forced_root_moves]
        best_score = -self.config.infinity_score
        best_move: Move | None = None
        root_scores: list[RootMoveScore] = []

        for move_index, move in enumerate(moves):
            self._force_timeout_check()
            moving_player = position.current_player
            position.make_move(*move)
            try:
                if (
                    self.config.enable_pvs
                    and self.config.enable_alpha_beta
                    and move_index > 0
                ):
                    score = -self._negamax(
                        position,
                        depth - 1,
                        -alpha - 1,
                        -alpha,
                        ply=1,
                        color=-1,
                        extension_depth=self.config.threat_extension_depth,
                    )
                    if alpha < score < beta:
                        score = -self._negamax(
                            position,
                            depth - 1,
                            -beta,
                            -alpha,
                            ply=1,
                            color=-1,
                            extension_depth=self.config.threat_extension_depth,
                        )
                else:
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
            root_scores.append(RootMoveScore(move, score))
            if self.config.enable_alpha_beta and score > alpha:
                alpha = score
            if self.config.enable_alpha_beta and alpha >= beta:
                self._record_cutoff(moving_player, move, depth, 0)
                self._beta_cutoffs += 1
                break

        self._latest_root_scores = sorted(
            root_scores,
            key=lambda item: (-item.score, item.move[0], item.move[1]),
        )
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
        self._max_ply = max(self._max_ply, ply)
        if (
            self.config.max_nodes is not None
            and self._nodes > self.config.max_nodes
        ):
            raise SearchTimeout
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
                        self._tt_cutoffs += 1
                        return tt_score

        if depth <= 0:
            return self._quiescence(
                position,
                alpha,
                beta,
                ply=ply,
                color=color,
                extension_depth=extension_depth,
                tt_move=tt_move,
            )

        moves = self.candidates.generate(
            position,
            root=False,
            tt_move=tt_move,
            timeout_check=self._force_timeout_check,
            ordering_bonus=lambda move: self._ordering_bonus(
                position.current_player,
                move,
                ply,
            ),
        )
        next_depth = depth - 1
        next_extension = extension_depth

        if not moves:
            return color * self._evaluate(position)

        best_score = -self.config.infinity_score
        best_move: Move | None = None
        for move_index, move in enumerate(moves):
            moving_player = position.current_player
            position.make_move(*move)
            try:
                if (
                    self.config.enable_pvs
                    and self.config.enable_alpha_beta
                    and move_index > 0
                ):
                    score = -self._negamax(
                        position,
                        next_depth,
                        -alpha - 1,
                        -alpha,
                        ply=ply + 1,
                        color=-color,
                        extension_depth=next_extension,
                    )
                    if alpha < score < beta:
                        score = -self._negamax(
                            position,
                            next_depth,
                            -beta,
                            -alpha,
                            ply=ply + 1,
                            color=-color,
                            extension_depth=next_extension,
                        )
                else:
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
                self._record_cutoff(moving_player, move, depth, ply)
                self._beta_cutoffs += 1
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

    def _quiescence(
        self,
        position: SearchPosition,
        alpha: int,
        beta: int,
        *,
        ply: int,
        color: int,
        extension_depth: int,
        tt_move: Move | None,
    ) -> int:
        self._quiescence_nodes += 1
        original_alpha = alpha
        original_beta = beta
        player = position.current_player
        own_wins = self.candidates.immediate_wins(
            position,
            player,
            self._force_timeout_check,
        )
        opponent_wins = self.candidates.immediate_wins(
            position,
            player.opponent,
            self._force_timeout_check,
        )

        mandatory = bool(own_wins or opponent_wins)
        if own_wins:
            moves = list(own_wins)
        elif opponent_wins:
            moves = list(opponent_wins)
        elif extension_depth > 0:
            moves = self.candidates.generate(
                position,
                root=False,
                tt_move=tt_move,
                forcing_only=True,
                timeout_check=self._force_timeout_check,
                ordering_bonus=lambda move: self._ordering_bonus(player, move, ply),
            )
        else:
            moves = []

        stand_pat = color * self._evaluate(position)
        if not mandatory:
            if extension_depth <= 0 or not moves:
                return stand_pat
            if self.config.enable_alpha_beta and stand_pat >= beta:
                return stand_pat
            best_score = stand_pat
            if self.config.enable_alpha_beta:
                alpha = max(alpha, stand_pat)
        else:
            best_score = -self.config.infinity_score

        best_move: Move | None = None
        for move in moves:
            moving_player = position.current_player
            position.make_move(*move)
            try:
                score = -self._negamax(
                    position,
                    0,
                    -beta,
                    -alpha,
                    ply=ply + 1,
                    color=-color,
                    extension_depth=max(0, extension_depth - 1),
                )
            finally:
                position.undo_move()
            if score > best_score:
                best_score = score
                best_move = move
            if self.config.enable_alpha_beta:
                alpha = max(alpha, score)
                if alpha >= beta:
                    self._record_cutoff(moving_player, move, 1, ply)
                    self._beta_cutoffs += 1
                    break

        bound = self._bound_type(best_score, original_alpha, original_beta)
        self.transposition_table.store(
            TranspositionEntry(
                key=position.hash_key,
                depth=0,
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

    def _evaluate(self, position: SearchPosition) -> int:
        key = (position.hash_key, self._perspective)
        cached = self._evaluation_cache.get(key)
        if cached is not None:
            self._eval_cache_hits += 1
            self._evaluation_cache.move_to_end(key)
            return cached
        score = self.evaluator.evaluate(
            position,
            self._perspective,
            self._force_timeout_check,
        )
        if self.config.evaluation_cache_capacity > 0:
            self._evaluation_cache[key] = score
            self._evaluation_cache.move_to_end(key)
            while len(self._evaluation_cache) > self.config.evaluation_cache_capacity:
                self._evaluation_cache.popitem(last=False)
        return score

    def _position_patterns(
        self,
        position: SearchPosition,
        player: Player,
    ):
        self._force_timeout_check()
        state = position.evaluation_state
        patterns_for = getattr(state, "patterns_for", None)
        if patterns_for is not None:
            return patterns_for(player)
        return self.matcher.find_patterns(
            position,
            player,
            self._force_timeout_check,
        )

    def _ordering_bonus(self, player: Player, move: Move, ply: int) -> int:
        bonus = self._history.get((player, move), 0)
        if move in self._killers.get(ply, ()):
            bonus += self.config.killer_move_bonus
        return bonus

    def _record_cutoff(
        self,
        player: Player,
        move: Move,
        depth: int,
        ply: int,
    ) -> None:
        history_key = (player, move)
        increment = self.config.history_bonus * max(1, depth) ** 2
        self._history[history_key] = min(
            self.config.history_max,
            self._history.get(history_key, 0) + increment,
        )
        killers = self._killers.setdefault(ply, [])
        if move in killers:
            killers.remove(move)
        killers.insert(0, move)
        del killers[2:]

    def _check_timeout(self) -> None:
        interval = max(1, self.config.timeout_check_interval_nodes)
        if self._nodes % interval == 0:
            self._force_timeout_check()

    def _force_timeout_check(self) -> None:
        if (
            self._cancel_event is not None
            and self._cancel_event.is_set()
        ) or self.clock() >= self._deadline:
            raise SearchTimeout

    def _vcf_timeout_check(self) -> None:
        if (
            self._cancel_event is not None
            and self._cancel_event.is_set()
        ) or self.clock() >= self._vcf_deadline:
            raise VCFTimeout

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
            beta_cutoffs=self._beta_cutoffs,
            tt_cutoffs=self._tt_cutoffs,
            eval_cache_hits=self._eval_cache_hits,
            quiescence_nodes=self._quiescence_nodes,
            max_ply=self._max_ply,
            tt_collisions=(
                self.transposition_table.collisions - self._tt_collision_start
            ),
            tt_replacements=(
                self.transposition_table.replacements - self._tt_replacement_start
            ),
            vcf_found=self._vcf_found,
            vcf_nodes=self._vcf_nodes,
            defensive_vcf_detected=self._defensive_vcf_detected,
            defensive_vcf_moves=self._defensive_vcf_moves,
            depth_results=tuple(self._depth_results),
            root_moves=tuple(self._completed_root_scores),
        )
        return move

    def _center_distance(self, size: int, move: Move) -> float:
        center = (size - 1) / 2
        return max(abs(move[0] - center), abs(move[1] - center))
