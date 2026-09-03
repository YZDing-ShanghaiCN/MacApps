"""Configuration for the deterministic HardAI tactical + MCTS engine."""

from __future__ import annotations

from dataclasses import dataclass

from gomoku.config import BOARD_SIZE


@dataclass(frozen=True)
class HardAIConfig:
    """All tunable HardAI values.

    Tests can create adjusted copies with ``dataclasses.replace`` without
    changing production defaults or scattering search constants.
    """

    board_size: int = BOARD_SIZE
    time_limit_ms: int = 800
    time_safety_margin_ms: int = 20
    # Budget slices of the usable time. Unused tactical slices roll forward
    # into MCTS; time_safety_margin_ms always stays reserved.
    vcf_time_fraction: float = 0.25
    vct_time_fraction: float = 0.45
    defense_time_fraction: float = 0.5
    defense_verify_budget_fraction: float = 0.5
    mcts_min_time_ms: int = 10

    vcf_max_depth: int = 8
    vct_max_depth: int = 6
    candidate_radius: int = 2
    pattern_line_cache_capacity: int = 100_000
    threat_transposition_capacity: int = 100_000
    vct_defender_reply_cap: int = 12
    defense_candidate_cap: int = 24
    timeout_check_interval_nodes: int = 32

    mcts_exploration_constant: float = 1.5
    mcts_seed: int = 20240903
    mcts_min_simulations: int = 0
    mcts_node_capacity: int = 200_000
    mcts_reuse_root: bool = True
    mcts_priority_prior_bonus: float = 4.0
    mcts_uniform_prior_epsilon: float = 0.05

    policy_temperature: float = 1.0
    value_scale: float = 100_000.0
    zobrist_seed: int = 0x9E37_79B9_7F4A_7C15
    enable_tactical_precheck: bool = True

    def __post_init__(self) -> None:
        if self.time_limit_ms <= 0:
            raise ValueError("time_limit_ms must be positive.")
        if self.time_safety_margin_ms < 0:
            raise ValueError("time_safety_margin_ms must be non-negative.")
        if self.time_safety_margin_ms >= self.time_limit_ms:
            raise ValueError(
                "time_safety_margin_ms must be smaller than time_limit_ms."
            )
        if not 0.0 <= self.vcf_time_fraction <= 1.0:
            raise ValueError("vcf_time_fraction must be within [0, 1].")
        if not 0.0 <= self.vct_time_fraction <= 1.0:
            raise ValueError("vct_time_fraction must be within [0, 1].")
        if self.vcf_time_fraction + self.vct_time_fraction > 1.0:
            raise ValueError(
                "vcf_time_fraction + vct_time_fraction must not exceed 1.0."
            )
        if not 0.0 < self.defense_time_fraction <= 1.0:
            raise ValueError("defense_time_fraction must be within (0, 1].")
        if not 0.0 < self.defense_verify_budget_fraction <= 1.0:
            raise ValueError(
                "defense_verify_budget_fraction must be within (0, 1]."
            )
        if self.vcf_max_depth < 2 or self.vct_max_depth < 2:
            raise ValueError("tactical max depths must be at least 2.")
        if self.threat_transposition_capacity < 0:
            raise ValueError("threat_transposition_capacity must be >= 0.")
        if self.vct_defender_reply_cap <= 0 or self.defense_candidate_cap <= 0:
            raise ValueError("reply and defense caps must be positive.")
        if self.mcts_exploration_constant < 0.0:
            raise ValueError("mcts_exploration_constant must be >= 0.")
        if not 0.0 <= self.mcts_uniform_prior_epsilon <= 1.0:
            raise ValueError("mcts_uniform_prior_epsilon must be within [0, 1].")
        if self.policy_temperature <= 0.0 or self.value_scale <= 0.0:
            raise ValueError("policy_temperature and value_scale must be positive.")


DEFAULT_HARD_AI_CONFIG = HardAIConfig()
