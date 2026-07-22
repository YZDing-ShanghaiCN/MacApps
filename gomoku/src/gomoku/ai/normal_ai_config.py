"""Central configuration for the deterministic NormalAI search engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from gomoku.config import BOARD_SIZE


DEFAULT_PATTERN_SCORES = {
    "five": 100_000_000,
    "open_four": 1_000_000,
    "closed_four": 25_000,
    "open_three": 20_000,
    "jump_three": 15_000,
    "closed_three": 3_000,
    "open_two": 500,
    "closed_two": 80,
}


@dataclass(frozen=True)
class NormalAIConfig:
    """All tunable NormalAI values.

    Tests can create adjusted copies with ``dataclasses.replace`` without
    changing production defaults or scattering search constants.
    """

    board_size: int = BOARD_SIZE
    time_limit_ms: int = 800
    time_safety_margin_ms: int = 3
    max_depth: int = 6
    candidate_radius: int = 2
    root_max_quiet_candidates: int = 20
    inner_max_quiet_candidates: int = 12
    transposition_capacity: int = 200_000
    transposition_bucket_size: int = 4
    threat_extension_depth: int = 2
    timeout_check_interval_nodes: int = 32
    zobrist_seed: int = 0x5A17_2026
    enable_alpha_beta: bool = True
    enable_pvs: bool = True
    aspiration_window: int = 50_000
    max_nodes: int | None = None
    evaluation_cache_capacity: int = 50_000
    pattern_line_cache_capacity: int = 100_000

    enable_vcf: bool = True
    vcf_max_depth: int = 8
    vcf_time_fraction: float = 0.18
    enable_defensive_vcf: bool = True
    defensive_vcf_time_fraction: float = 0.12
    vcf_defense_max_candidates: int = 16
    enable_dynamic_vcf_budget: bool = True
    vcf_min_budget_scale: float = 0.35
    vcf_multiple_threat_budget_bonus: float = 0.15
    vcf_pattern_budget_scales: Mapping[str, float] = field(
        default_factory=lambda: {
            "closed_four": 1.0,
            "open_three": 1.0,
            "jump_three": 0.85,
            "closed_three": 0.45,
        }
    )

    mate_score: int = 1_000_000_000
    infinity_score: int = 2_000_000_000
    evaluation_ceiling: int = 900_000_000

    attack_factor: float = 1.0
    defense_factor: float = 1.05
    center_bonus: int = 12
    center_bonus_full_until_moves: int = 10
    center_bonus_zero_after_moves: int = 36
    double_threat_bonus: int = 50_000
    pattern_scores: Mapping[str, int] = field(
        default_factory=lambda: dict(DEFAULT_PATTERN_SCORES)
    )
    defense_pattern_scores: Mapping[str, int] = field(
        default_factory=lambda: dict(DEFAULT_PATTERN_SCORES)
    )

    # Candidate ordering values are deliberately separate from static scores.
    immediate_win_order: int = 9_000_000
    immediate_block_order: int = 8_000_000
    double_threat_order: int = 7_000_000
    open_four_order: int = 6_000_000
    closed_four_order: int = 5_000_000
    open_three_order: int = 4_000_000
    block_open_three_order: int = 3_000_000
    local_pattern_order_scale: int = 100
    history_bonus: int = 64
    history_max: int = 1_000_000
    killer_move_bonus: int = 2_000_000


DEFAULT_NORMAL_AI_CONFIG = NormalAIConfig()
