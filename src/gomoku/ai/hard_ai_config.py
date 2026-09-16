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

    mcts_exploration_constant: float = 1.5
    mcts_seed: int = 20240903
    mcts_min_simulations: int = 0
    mcts_node_capacity: int = 200_000
    mcts_reuse_root: bool = True
    mcts_priority_prior_bonus: float = 4.0
    mcts_uniform_prior_epsilon: float = 0.05
    # One-move tactical probes at MCTS leaf creation (immediate win,
    # mandatory block, double four). Bounded and cheap; the top-level
    # VCF/VCT engine stays authoritative.
    mcts_leaf_tactics_enabled: bool = True

    # Progressive widening: a node starts with the first
    # mcts_pw_initial_children pool moves as untried and admits more as its
    # visit count grows (initial + int(growth * sqrt(visits))). Disabling
    # exposes the whole pool at once (the pre-widening behavior).
    mcts_pw_enabled: bool = True
    mcts_pw_initial_children: int = 24
    mcts_pw_growth: float = 8.0

    # When > 0, the model provider contributes its top-k legal moves over
    # the full board to every expansion pool (union with the local tactical
    # pool and priority moves). Heuristic mode ignores this cheaply.
    mcts_global_top_k: int = 16

    policy_temperature: float = 1.0
    value_scale: float = 100_000.0
    zobrist_seed: int = 0x9E37_79B9_7F4A_7C15

    # AlphaZero-style root Dirichlet noise. Only the self-play generator
    # enables it (MCTS.search(..., root_noise=True) with the game RNG);
    # HardAI game play, tactical search and the arena never apply it.
    selfplay_dirichlet_enabled: bool = False
    selfplay_dirichlet_epsilon: float = 0.25
    selfplay_dirichlet_alpha: float = 0.03

    # Path to a trained policy-value network (save_model output). None
    # keeps the heuristic provider; the model provider imports torch
    # lazily, so the core game never requires ML dependencies.
    model_path: str | None = None

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
        if self.mcts_exploration_constant < 0.0:
            raise ValueError("mcts_exploration_constant must be >= 0.")
        if self.mcts_node_capacity < 0:
            raise ValueError("mcts_node_capacity must be >= 0.")
        if not 0.0 <= self.mcts_uniform_prior_epsilon <= 1.0:
            raise ValueError("mcts_uniform_prior_epsilon must be within [0, 1].")
        if self.mcts_pw_initial_children < 1:
            raise ValueError("mcts_pw_initial_children must be >= 1.")
        if self.mcts_pw_growth < 0.0:
            raise ValueError("mcts_pw_growth must be >= 0.")
        if self.mcts_global_top_k < 0:
            raise ValueError("mcts_global_top_k must be >= 0.")
        if self.policy_temperature <= 0.0 or self.value_scale <= 0.0:
            raise ValueError("policy_temperature and value_scale must be positive.")
        if not 0.0 <= self.selfplay_dirichlet_epsilon <= 1.0:
            raise ValueError(
                "selfplay_dirichlet_epsilon must be within [0, 1]."
            )
        if self.selfplay_dirichlet_alpha <= 0.0:
            raise ValueError("selfplay_dirichlet_alpha must be positive.")
        if self.model_path is not None and not self.model_path.strip():
            raise ValueError("model_path must be a non-empty path or None.")


DEFAULT_HARD_AI_CONFIG = HardAIConfig()
