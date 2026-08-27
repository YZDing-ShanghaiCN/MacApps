"""Central configuration for the rule-based SimpleAI."""

from __future__ import annotations

from dataclasses import dataclass


TIE_BREAK_STABLE = "stable"
TIE_BREAK_VARIED = "varied"
VALID_TIE_BREAK_MODES = (TIE_BREAK_STABLE, TIE_BREAK_VARIED)


@dataclass(frozen=True)
class SimpleAIConfig:
    """All tunable values used by the easy-difficulty AI.

    ``varied`` uses an instance-local pseudo-random generator, so equivalent
    choices can vary while remaining reproducible from ``random_seed``.
    ``stable`` always selects the first deterministically ordered choice.
    """

    tie_break_mode: str = TIE_BREAK_VARIED
    random_seed: int = 0x51A1_2026
    fallback_radius: int = 2
    fallback_own_neighbor_weight: int = 2
    fallback_opponent_neighbor_weight: int = 1
    fallback_center_weight: int = 1

    def __post_init__(self) -> None:
        if self.tie_break_mode not in VALID_TIE_BREAK_MODES:
            raise ValueError(
                f"tie_break_mode must be one of: {', '.join(VALID_TIE_BREAK_MODES)}."
            )
        if self.fallback_radius < 1:
            raise ValueError("fallback_radius must be at least 1.")


DEFAULT_SIMPLE_AI_CONFIG = SimpleAIConfig()
