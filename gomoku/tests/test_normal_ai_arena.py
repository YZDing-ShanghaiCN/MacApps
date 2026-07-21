from dataclasses import replace
from pathlib import Path
import json
import sys


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from gomoku.ai.arena import compare_configs, load_config, play_game
from gomoku.ai.normal_ai_config import DEFAULT_NORMAL_AI_CONFIG


def test_load_config_merges_pattern_scores(tmp_path) -> None:
    path = tmp_path / "candidate.json"
    path.write_text(
        json.dumps({"pattern_scores": {"closed_four": 42_000}}),
        encoding="utf-8",
    )

    config = load_config(path, DEFAULT_NORMAL_AI_CONFIG)

    assert config.pattern_scores["closed_four"] == 42_000
    assert config.pattern_scores["open_four"] == (
        DEFAULT_NORMAL_AI_CONFIG.pattern_scores["open_four"]
    )


def test_tiny_arena_game_is_legal_and_bounded() -> None:
    config = replace(
        DEFAULT_NORMAL_AI_CONFIG,
        max_depth=2,
        enable_vcf=False,
        enable_defensive_vcf=False,
    )
    result = play_game(
        config,
        config,
        black_label="A",
        white_label="B",
        node_budget=20,
        max_moves=4,
    )

    assert result.move_count == 4
    assert result.winner is None
    assert result.searches["A"] == 2
    assert result.searches["B"] == 2


def test_compare_configs_swaps_colors() -> None:
    config = replace(
        DEFAULT_NORMAL_AI_CONFIG,
        max_depth=1,
        enable_vcf=False,
        enable_defensive_vcf=False,
    )
    summary = compare_configs(
        config,
        config,
        node_budget=10,
        max_moves=2,
        openings=((),),
    )

    assert summary.games == 2
    assert summary.draws == 2
    assert summary.wins == {"A": 0, "B": 0}
