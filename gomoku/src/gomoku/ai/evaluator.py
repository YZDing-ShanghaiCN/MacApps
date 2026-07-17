"""Static evaluation for NormalAI search leaves."""

from __future__ import annotations

from collections.abc import Callable

from gomoku.ai.normal_ai_config import NormalAIConfig
from gomoku.ai.pattern_matcher import Pattern, PatternKind, PatternMatcher
from gomoku.core.board import Board
from gomoku.core.enums import Player


THREAT_KINDS = {
    PatternKind.OPEN_FOUR,
    PatternKind.CLOSED_FOUR,
    PatternKind.OPEN_THREE,
    PatternKind.JUMP_THREE,
}


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
        full_until = self.config.center_bonus_full_until_moves
        zero_after = max(full_until + 1, self.config.center_bonus_zero_after_moves)
        if occupied_count <= full_until:
            phase_factor = 1.0
        elif occupied_count >= zero_after:
            phase_factor = 0.0
        else:
            phase_factor = (zero_after - occupied_count) / (zero_after - full_until)
        score = 0
        for row in range(board.size):
            for col in range(board.size):
                if board.grid[row][col] != int(player):
                    continue
                distance = max(abs(row - center), abs(col - center))
                score += int(
                    (center + 1 - distance)
                    * self.config.center_bonus
                    * phase_factor
                )
        return score
