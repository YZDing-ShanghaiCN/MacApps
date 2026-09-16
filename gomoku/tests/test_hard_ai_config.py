from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import sys

import pytest


SRC_DIR = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SRC_DIR))

from gomoku.ai.hard_ai_config import DEFAULT_HARD_AI_CONFIG, HardAIConfig


def test_default_values() -> None:
    config = DEFAULT_HARD_AI_CONFIG
    assert config.time_limit_ms == 800
    assert config.time_safety_margin_ms == 20
    assert config.vcf_time_fraction == 0.25
    assert config.vct_time_fraction == 0.45
    assert config.vcf_time_fraction + config.vct_time_fraction <= 1.0
    assert config.vcf_max_depth >= 2
    assert config.vct_max_depth >= 2
    assert config.threat_transposition_capacity > 0
    assert config.mcts_exploration_constant >= 0.0
    assert config.board_size == 15


def test_removed_corrective_fields_are_gone() -> None:
    config = DEFAULT_HARD_AI_CONFIG
    assert not hasattr(config, "enable_tactical_precheck")
    assert not hasattr(config, "vct_defender_reply_cap")
    assert not hasattr(config, "defense_candidate_cap")
    assert not hasattr(config, "timeout_check_interval_nodes")


def test_config_is_immutable() -> None:
    with pytest.raises(FrozenInstanceError):
        DEFAULT_HARD_AI_CONFIG.time_limit_ms = 100  # type: ignore[misc]


def test_replace_creates_adjusted_copy() -> None:
    config = replace(DEFAULT_HARD_AI_CONFIG, time_limit_ms=150, vct_max_depth=4)
    assert config.time_limit_ms == 150
    assert config.vct_max_depth == 4
    assert config.vcf_time_fraction == DEFAULT_HARD_AI_CONFIG.vcf_time_fraction


@pytest.mark.parametrize(
    "updates",
    [
        {"time_limit_ms": 0},
        {"time_safety_margin_ms": -1},
        {"time_safety_margin_ms": 800},
        {"vcf_time_fraction": 1.5},
        {"vct_time_fraction": -0.1},
        {"vcf_time_fraction": 0.8, "vct_time_fraction": 0.8},
        {"defense_time_fraction": 0.0},
        {"defense_verify_budget_fraction": 2.0},
        {"vcf_max_depth": 1},
        {"vct_max_depth": 0},
        {"threat_transposition_capacity": -1},
        {"mcts_exploration_constant": -0.5},
        {"mcts_node_capacity": -1},
        {"mcts_uniform_prior_epsilon": 1.5},
        {"policy_temperature": 0.0},
        {"value_scale": -1.0},
    ],
)
def test_invalid_values_raise(updates) -> None:
    with pytest.raises(ValueError):
        replace(DEFAULT_HARD_AI_CONFIG, **updates)
