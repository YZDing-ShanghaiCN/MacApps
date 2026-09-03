"""Policy and value estimates for the HardAI MCTS fallback.

``HeuristicPolicyValueProvider`` scores candidate moves with the existing
static evaluator (NormalAI's hand-tuned score table, reused read-only as
heuristic data) and maps scores into a probability distribution over moves
and a win probability in ``(0, 1)``. It is deterministic and has no ML
dependencies. A trained-model provider can replace it by implementing the
same :class:`PolicyValueProvider` protocol.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Protocol

from gomoku.ai.evaluator import IncrementalEvaluationState, StaticEvaluator
from gomoku.ai.hard_ai_config import HardAIConfig
from gomoku.ai.normal_ai_config import DEFAULT_NORMAL_AI_CONFIG
from gomoku.ai.pattern_matcher import PatternMatcher
from gomoku.ai.search_position import SearchPosition
from gomoku.core.board import Board
from gomoku.core.enums import Player

Move = tuple[int, int]


class PolicyValueProvider(Protocol):
    """Pluggable policy/value source (heuristic now, model later)."""

    def policy(
        self,
        position: SearchPosition,
        player: Player | int,
        legal_moves: list[Move],
        *,
        timeout_check: Callable[[], None] | None = None,
    ) -> dict[Move, float]: ...

    def value(
        self,
        position: SearchPosition,
        player: Player | int,
        *,
        timeout_check: Callable[[], None] | None = None,
    ) -> float: ...


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


class HeuristicPolicyValueProvider:
    """Static-evaluator based priors and values, deterministic everywhere."""

    def __init__(
        self,
        config: HardAIConfig,
        *,
        evaluator=None,
        matcher: PatternMatcher | None = None,
    ) -> None:
        self.config = config
        self.matcher = matcher or PatternMatcher(
            config.pattern_line_cache_capacity
        )
        self.evaluator = evaluator or StaticEvaluator(
            DEFAULT_NORMAL_AI_CONFIG, self.matcher
        )

    def _incremental_state(
        self, position: SearchPosition
    ) -> IncrementalEvaluationState:
        state = getattr(position, "evaluation_state", None)
        if (
            isinstance(state, IncrementalEvaluationState)
            and state.evaluator is self.evaluator
        ):
            return state
        return self.evaluator.prepare(position)

    def policy(
        self,
        position: SearchPosition,
        player: Player | int,
        legal_moves: list[Move],
        *,
        timeout_check: Callable[[], None] | None = None,
    ) -> dict[Move, float]:
        """Softmax prior over ``legal_moves`` by one-ply static score.

        The input board is left untouched: probes place the move
        temporarily and restore it in ``finally``. Scoring reuses the
        evaluator's incremental state, so a probe only refreshes the four
        lines through the move.
        """
        mover = Player(player)
        state = self._incremental_state(position)
        scale = self.config.value_scale * self.config.policy_temperature
        scores: dict[Move, float] = {}
        for move in sorted(legal_moves):
            if timeout_check is not None:
                timeout_check()
            row, col = move
            position.grid[row][col] = int(mover)
            try:
                state.apply_move(row, col, mover)
                scores[move] = float(state.evaluate(mover))
                state.undo_move(row, col, mover)
            finally:
                position.grid[row][col] = int(Player.EMPTY)
        if not scores:
            return {}
        maximum = max(scores.values())
        weights = {
            move: math.exp((score - maximum) / scale)
            for move, score in scores.items()
        }
        total = sum(weights.values())
        if total <= 0.0:
            share = 1.0 / len(weights)
            return {move: share for move in weights}
        return {move: weight / total for move, weight in weights.items()}

    def value(
        self,
        position: SearchPosition,
        player: Player | int,
        *,
        timeout_check: Callable[[], None] | None = None,
    ) -> float:
        """Win probability in (0, 1) from ``player``'s perspective."""
        if timeout_check is not None:
            timeout_check()
        if position.empty_count == 0:
            return 0.5
        score = self._incremental_state(position).evaluate(Player(player))
        return _sigmoid(score / self.config.value_scale)
