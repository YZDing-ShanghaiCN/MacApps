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

        own_score = self._pattern_score(own_patterns)
        opponent_score = self._pattern_score(opponent_patterns)
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

    def _pattern_score(self, patterns: tuple[Pattern, ...]) -> int:
        return sum(self.config.pattern_scores[pattern.kind.value] for pattern in patterns)

    def _multiple_threat_score(self, patterns: tuple[Pattern, ...]) -> int:
        directions = {
            pattern.direction
            for pattern in patterns
            if pattern.kind in THREAT_KINDS
        }
        return max(0, len(directions) - 1) * self.config.double_threat_bonus

    def _position_score(self, board: Board, player: Player) -> int:
        center = (board.size - 1) / 2
        score = 0
        for row in range(board.size):
            for col in range(board.size):
                if board.grid[row][col] != int(player):
                    continue
                distance = max(abs(row - center), abs(col - center))
                score += int((center + 1 - distance) * self.config.center_bonus)
        return score
