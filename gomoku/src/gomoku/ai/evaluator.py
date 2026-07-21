"""Static evaluation for NormalAI search leaves."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable

from gomoku.ai.normal_ai_config import NormalAIConfig
from gomoku.ai.pattern_matcher import Pattern, PatternKind, PatternMatcher
from gomoku.ai.search_position import SearchPosition
from gomoku.core.board import Board
from gomoku.core.enums import Player


THREAT_KINDS = {
    PatternKind.OPEN_FOUR,
    PatternKind.CLOSED_FOUR,
    PatternKind.OPEN_THREE,
    PatternKind.JUMP_THREE,
}


class IncrementalEvaluationState:
    """Reversible line scores shared by evaluation and move generation."""

    def __init__(
        self,
        evaluator: "StaticEvaluator",
        position: SearchPosition,
        timeout_check: Callable[[], None] | None = None,
    ) -> None:
        self.evaluator = evaluator
        self.position = position
        self.config = evaluator.config
        self.matcher = evaluator.matcher
        self.occupied_count = len(position.occupied)
        self.offense_scores = {Player.BLACK: 0, Player.WHITE: 0}
        self.defense_scores = {Player.BLACK: 0, Player.WHITE: 0}
        self.center_raw = {Player.BLACK: 0.0, Player.WHITE: 0.0}
        self.threat_identities = {
            Player.BLACK: Counter(),
            Player.WHITE: Counter(),
        }
        self._line_patterns: dict[
            tuple[tuple[int, int], tuple[tuple[int, int], ...], Player],
            tuple[Pattern, ...],
        ] = {}
        self._lines_by_cell: dict[
            tuple[int, int],
            list[tuple[tuple[int, int], tuple[tuple[int, int], ...]]],
        ] = {}
        self._pattern_cache: dict[Player, tuple[Pattern, ...] | None] = {
            Player.BLACK: None,
            Player.WHITE: None,
        }

        center = (position.size - 1) / 2
        for row, col in position.occupied:
            player = Player(position.grid[row][col])
            distance = max(abs(row - center), abs(col - center))
            self.center_raw[player] += center + 1 - distance

        for direction, line in self.matcher.iter_lines(position):
            if timeout_check is not None:
                timeout_check()
            descriptor = (direction, line)
            for cell in line:
                self._lines_by_cell.setdefault(cell, []).append(descriptor)
            for player in (Player.BLACK, Player.WHITE):
                patterns = self.matcher.find_patterns_in_line(
                    position,
                    line,
                    direction,
                    player,
                )
                self._line_patterns[(direction, line, player)] = patterns
                self._add_patterns(player, patterns)

    def apply_move(self, row: int, col: int, player: Player) -> None:
        self.occupied_count += 1
        self.center_raw[player] += self._center_weight(row, col)
        self._refresh_lines(row, col)

    def undo_move(self, row: int, col: int, player: Player) -> None:
        self.occupied_count -= 1
        self.center_raw[player] -= self._center_weight(row, col)
        self._refresh_lines(row, col)

    def patterns_for(self, player: Player | int) -> tuple[Pattern, ...]:
        player_value = Player(player)
        cached = self._pattern_cache[player_value]
        if cached is None:
            cached = tuple(
                pattern
                for (direction, line, owner), patterns in self._line_patterns.items()
                if owner == player_value
                for pattern in patterns
            )
            self._pattern_cache[player_value] = cached
        return cached

    def evaluate(
        self,
        perspective: Player,
        timeout_check: Callable[[], None] | None = None,
    ) -> int:
        if timeout_check is not None:
            timeout_check()
        opponent = perspective.opponent
        own_score = self.offense_scores[perspective]
        opponent_score = self.defense_scores[opponent]
        own_score += self._multiple_threat_score(perspective)
        opponent_score += self._multiple_threat_score(opponent)
        positional = self._position_score(perspective) - self._position_score(opponent)
        value = int(
            own_score * self.config.attack_factor
            - opponent_score * self.config.defense_factor
            + positional
        )
        ceiling = self.config.evaluation_ceiling
        return max(-ceiling, min(ceiling, value))

    def _refresh_lines(self, row: int, col: int) -> None:
        for direction, line in self._lines_by_cell.get((row, col), ()):
            for player in (Player.BLACK, Player.WHITE):
                key = (direction, line, player)
                self._remove_patterns(player, self._line_patterns[key])
                patterns = self.matcher.find_patterns_in_line(
                    self.position,
                    line,
                    direction,
                    player,
                )
                self._line_patterns[key] = patterns
                self._add_patterns(player, patterns)
                self._pattern_cache[player] = None

    def _add_patterns(
        self,
        player: Player,
        patterns: tuple[Pattern, ...],
    ) -> None:
        for pattern in patterns:
            self.offense_scores[player] += self.config.pattern_scores[
                pattern.kind.value
            ]
            self.defense_scores[player] += self.config.defense_pattern_scores[
                pattern.kind.value
            ]
            if pattern.kind in THREAT_KINDS:
                self.threat_identities[player][pattern.identity] += 1

    def _remove_patterns(
        self,
        player: Player,
        patterns: tuple[Pattern, ...],
    ) -> None:
        for pattern in patterns:
            self.offense_scores[player] -= self.config.pattern_scores[
                pattern.kind.value
            ]
            self.defense_scores[player] -= self.config.defense_pattern_scores[
                pattern.kind.value
            ]
            if pattern.kind in THREAT_KINDS:
                identities = self.threat_identities[player]
                identities[pattern.identity] -= 1
                if identities[pattern.identity] <= 0:
                    del identities[pattern.identity]

    def _multiple_threat_score(self, player: Player) -> int:
        return max(0, len(self.threat_identities[player]) - 1) * (
            self.config.double_threat_bonus
        )

    def _position_score(self, player: Player) -> int:
        return int(
            self.center_raw[player]
            * self.config.center_bonus
            * self.evaluator._phase_factor(self.occupied_count)
        )

    def _center_weight(self, row: int, col: int) -> float:
        center = (self.position.size - 1) / 2
        return center + 1 - max(abs(row - center), abs(col - center))


class StaticEvaluator:
    def __init__(self, config: NormalAIConfig, matcher: PatternMatcher) -> None:
        self.config = config
        self.matcher = matcher

    def evaluate(
        self,
        board: Board,
        perspective: Player | int,
        timeout_check: Callable[[], None] | None = None,
    ) -> int:
        player = Player(perspective)
        incremental = getattr(board, "evaluation_state", None)
        if (
            isinstance(incremental, IncrementalEvaluationState)
            and incremental.evaluator is self
        ):
            return incremental.evaluate(player, timeout_check)
        opponent = player.opponent
        own_patterns = self.matcher.find_patterns(board, player, timeout_check)
        opponent_patterns = self.matcher.find_patterns(
            board,
            opponent,
            timeout_check,
        )

        own_score = self._pattern_score(own_patterns, defensive=False)
        opponent_score = self._pattern_score(opponent_patterns, defensive=True)
        own_score += self._multiple_threat_score(own_patterns)
        opponent_score += self._multiple_threat_score(opponent_patterns)

        positional = self._position_score(board, player) - self._position_score(
            board,
            opponent,
        )
        value = int(
            own_score * self.config.attack_factor
            - opponent_score * self.config.defense_factor
            + positional
        )
        ceiling = self.config.evaluation_ceiling
        return max(-ceiling, min(ceiling, value))

    def prepare(
        self,
        position: SearchPosition,
        timeout_check: Callable[[], None] | None = None,
    ) -> IncrementalEvaluationState:
        state = IncrementalEvaluationState(self, position, timeout_check)
        position.attach_evaluation_state(state)
        return state

    def _pattern_score(
        self,
        patterns: tuple[Pattern, ...],
        *,
        defensive: bool,
    ) -> int:
        scores = (
            self.config.defense_pattern_scores
            if defensive
            else self.config.pattern_scores
        )
        return sum(scores[pattern.kind.value] for pattern in patterns)

    def _multiple_threat_score(self, patterns: tuple[Pattern, ...]) -> int:
        threats = {
            (
                pattern.direction,
                pattern.stones,
                pattern.key_empties,
            )
            for pattern in patterns
            if pattern.kind in THREAT_KINDS
        }
        return max(0, len(threats) - 1) * self.config.double_threat_bonus

    def _position_score(self, board: Board, player: Player) -> int:
        center = (board.size - 1) / 2
        occupied_count = board.size * board.size - sum(
            cell == int(Player.EMPTY)
            for row in board.grid
            for cell in row
        )
        raw_score = 0.0
        for row in range(board.size):
            for col in range(board.size):
                if board.grid[row][col] != int(player):
                    continue
                distance = max(abs(row - center), abs(col - center))
                raw_score += center + 1 - distance
        return int(
            raw_score
            * self.config.center_bonus
            * self._phase_factor(occupied_count)
        )

    def _phase_factor(self, occupied_count: int) -> float:
        full_until = self.config.center_bonus_full_until_moves
        zero_after = max(full_until + 1, self.config.center_bonus_zero_after_moves)
        if occupied_count <= full_until:
            return 1.0
        if occupied_count >= zero_after:
            return 0.0
        return (zero_after - occupied_count) / (zero_after - full_until)
