"""Threat-first deterministic candidate generation and ordering."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from gomoku.ai.normal_ai_config import NormalAIConfig
from gomoku.ai.pattern_matcher import PatternKind, PatternMatcher
from gomoku.ai.search_position import SearchPosition
from gomoku.core.enums import Player


Move = tuple[int, int]

FOUR_KINDS = {PatternKind.OPEN_FOUR, PatternKind.CLOSED_FOUR}
THREE_KINDS = {PatternKind.OPEN_THREE, PatternKind.JUMP_THREE}
TACTICAL_KINDS = FOUR_KINDS | THREE_KINDS


@dataclass(frozen=True)
class RankedMove:
    move: Move
    priority: int
    tactical: bool
    center_distance: float


class CandidateGenerator:
    def __init__(self, config: NormalAIConfig, matcher: PatternMatcher) -> None:
        self.config = config
        self.matcher = matcher

    def immediate_wins(
        self,
        position: SearchPosition,
        player: Player | int,
        timeout_check: Callable[[], None] | None = None,
    ) -> tuple[Move, ...]:
        wins = []
        for move in sorted(self._nearby_empty_moves(position, radius=1)):
            if timeout_check is not None:
                timeout_check()
            if position.move_wins(*move, player):
                wins.append(move)
        return tuple(self._sort_by_center(position, wins))

    def generate(
        self,
        position: SearchPosition,
        *,
        root: bool,
        tt_move: Move | None = None,
        forcing_only: bool = False,
        timeout_check: Callable[[], None] | None = None,
        ordering_bonus: Callable[[Move], int] | None = None,
        quiet_limit: int | None = None,
        full_width: bool = False,
    ) -> list[Move]:
        player = position.current_player
        opponent = player.opponent
        nearby = (
            {
                (row, col)
                for row in range(position.size)
                for col in range(position.size)
                if position.is_empty(row, col)
            }
            if full_width
            else self._nearby_empty_moves(
                position,
                self.config.candidate_radius,
            )
        )
        if not nearby:
            return []

        wins = set(self.immediate_wins(position, player, timeout_check))
        blocks = set(self.immediate_wins(position, opponent, timeout_check))

        own_patterns = self._position_patterns(position, player, timeout_check)
        opponent_patterns = self._position_patterns(
            position,
            opponent,
            timeout_check,
        )
        key_moves = {
            move
            for pattern in own_patterns + opponent_patterns
            if pattern.kind in TACTICAL_KINDS
            for move in pattern.key_empties
            if position.is_empty(*move)
        }
        # Quiescence-style extension follows threats already present in the
        # position. Ordinary nearby moves are considered by the main search,
        # but adding them here would turn every leaf into another full ply.
        moves = (key_moves | wins | blocks) if forcing_only else (
            nearby | key_moves | wins | blocks
        )
        if tt_move is not None and position.is_empty(*tt_move):
            moves.add(tt_move)

        ranked: list[RankedMove] = []
        for move in sorted(moves):
            if timeout_check is not None:
                timeout_check()
            priority, tactical = self._rank_move(
                position,
                move,
                player,
                opponent,
                wins,
                blocks,
                move in key_moves,
                timeout_check,
            )
            if ordering_bonus is not None:
                priority += ordering_bonus(move)
            if forcing_only and not tactical:
                continue
            ranked.append(
                RankedMove(
                    move,
                    priority,
                    tactical,
                    self._center_distance(position, move),
                )
            )

        ranked.sort(
            key=lambda item: (
                item.move != tt_move,
                -item.priority,
                item.center_distance,
                item.move[0],
                item.move[1],
            )
        )
        tactical_moves = [item.move for item in ranked if item.tactical]
        quiet_moves = [item.move for item in ranked if not item.tactical]
        if full_width:
            return tactical_moves + quiet_moves
        limit = quiet_limit
        if limit is None:
            limit = (
                self.config.root_max_quiet_candidates
                if root
                else self.config.inner_max_quiet_candidates
            )
        return tactical_moves + quiet_moves[:limit]

    def _rank_move(
        self,
        position: SearchPosition,
        move: Move,
        player: Player,
        opponent: Player,
        wins: set[Move],
        blocks: set[Move],
        is_key_move: bool,
        timeout_check: Callable[[], None] | None,
    ) -> tuple[int, bool]:
        if move in wins:
            return self.config.immediate_win_order, True
        if move in blocks:
            return self.config.immediate_block_order, True

        own_patterns = self._patterns_after_move(
            position,
            move,
            player,
            timeout_check,
        )
        opponent_patterns = self._patterns_after_move(
            position,
            move,
            opponent,
            timeout_check,
        )
        own_kinds = {pattern.kind for pattern in own_patterns}
        opponent_kinds = {pattern.kind for pattern in opponent_patterns}
        own_threats = {
            (pattern.direction, pattern.stones, pattern.key_empties)
            for pattern in own_patterns
            if pattern.kind in TACTICAL_KINDS
        }
        opponent_threats = {
            (pattern.direction, pattern.stones, pattern.key_empties)
            for pattern in opponent_patterns
            if pattern.kind in TACTICAL_KINDS
        }

        if len(own_threats) >= 2 or len(opponent_threats) >= 2:
            base = self.config.double_threat_order
            tactical = True
        elif PatternKind.OPEN_FOUR in own_kinds:
            base = self.config.open_four_order
            tactical = True
        elif PatternKind.CLOSED_FOUR in own_kinds:
            base = self.config.closed_four_order
            tactical = True
        elif own_kinds & THREE_KINDS:
            base = self.config.open_three_order
            tactical = True
        elif is_key_move or opponent_kinds & THREE_KINDS:
            base = self.config.block_open_three_order
            tactical = True
        else:
            base = 0
            tactical = False

        local_score = sum(
            self.config.pattern_scores[pattern.kind.value]
            for pattern in own_patterns
        )
        defensive_score = sum(
            self.config.defense_pattern_scores[pattern.kind.value]
            for pattern in opponent_patterns
        )
        local_score = int(local_score * self.config.attack_factor)
        defensive_score = int(defensive_score * self.config.defense_factor)
        order_scale = max(1, self.config.local_pattern_order_scale)
        return base + (local_score + defensive_score) // order_scale, tactical

    def _patterns_after_move(
        self,
        position: SearchPosition,
        move: Move,
        player: Player,
        timeout_check: Callable[[], None] | None,
    ):
        row, col = move
        position.grid[row][col] = int(player)
        try:
            return self.matcher.find_patterns_through_move(
                position,
                player,
                move,
                timeout_check,
            )
        finally:
            position.grid[row][col] = int(Player.EMPTY)

    def _position_patterns(
        self,
        position: SearchPosition,
        player: Player,
        timeout_check: Callable[[], None] | None,
    ):
        if timeout_check is not None:
            timeout_check()
        state = position.evaluation_state
        patterns_for = getattr(state, "patterns_for", None)
        if patterns_for is not None:
            return patterns_for(player)
        return self.matcher.find_patterns(position, player, timeout_check)

    def _nearby_empty_moves(
        self,
        position: SearchPosition,
        radius: int,
    ) -> set[Move]:
        return position.nearby_empty_moves(radius)

    def _sort_by_center(
        self,
        position: SearchPosition,
        moves: list[Move],
    ) -> list[Move]:
        return sorted(
            moves,
            key=lambda move: (
                self._center_distance(position, move),
                move[0],
                move[1],
            ),
        )

    def _center_distance(self, position: SearchPosition, move: Move) -> float:
        center = (position.size - 1) / 2
        return max(abs(move[0] - center), abs(move[1] - center))
