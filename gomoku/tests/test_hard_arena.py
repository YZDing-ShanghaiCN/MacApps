from dataclasses import replace
from pathlib import Path
import sys


SRC_DIR = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SRC_DIR))

from gomoku.ai.hard_ai import HardAI
from gomoku.ai.hard_arena import (
    compare_hard_configs,
    compare_hard_vs_normal,
    load_hard_config,
    play_hard_game,
)
from gomoku.ai.hard_ai_config import DEFAULT_HARD_AI_CONFIG
from gomoku.ai.normal_ai_config import DEFAULT_NORMAL_AI_CONFIG
from gomoku.core.enums import Player


def _tiny_hard() -> HardAI:
    return HardAI(
        Player.BLACK,
        config=replace(
            DEFAULT_HARD_AI_CONFIG,
            mcts_node_capacity=40,
        ),
        clock=lambda: 0.0,
    )


def test_tiny_hard_vs_hard_game_is_legal_and_bounded() -> None:
    result = play_hard_game(
        _tiny_hard(),
        _tiny_hard(),
        black_label="A",
        white_label="B",
        max_moves=6,
    )

    assert result.move_count == 6
    assert result.winner is None
    assert result.searches == {"A": 3, "B": 3}
    labels = [move.label for move in result.moves]
    assert labels == ["A", "B", "A", "B", "A", "B"]
    for move in result.moves:
        assert 0 <= move.row < 15 and 0 <= move.col < 15


def test_compare_hard_configs_swaps_colors() -> None:
    config = replace(
        DEFAULT_HARD_AI_CONFIG,
        mcts_node_capacity=40,
    )
    summary = compare_hard_configs(
        config,
        config,
        mcts_capacity=40,
        max_moves=6,
        openings=((),),
    )

    assert summary.games == 2
    assert summary.draws == 2
    assert summary.wins == {"A": 0, "B": 0}
    assert summary.recommended_label is None


def test_cross_engine_hard_vs_normal_completes() -> None:
    summary = compare_hard_vs_normal(
        replace(DEFAULT_HARD_AI_CONFIG, mcts_node_capacity=40),
        DEFAULT_NORMAL_AI_CONFIG,
        mcts_capacity=40,
        normal_node_budget=20,
        max_moves=4,
        openings=((),),
    )

    assert summary.games == 2
    total_searches = sum(
        record.searches[label]
        for record in summary.game_records
        for label in ("hard", "normal")
    )
    assert total_searches == 8
    assert set(summary.wins) == {"hard", "normal"}
    for record in summary.game_records:
        assert record.move_count == 4


def test_load_hard_config_merges_overrides(tmp_path) -> None:
    path = tmp_path / "candidate.json"
    path.write_text(
        '{"mcts_node_capacity": 42}',
        encoding="utf-8",
    )

    config = load_hard_config(path, DEFAULT_HARD_AI_CONFIG)

    assert config.mcts_node_capacity == 42
    assert config.time_limit_ms == DEFAULT_HARD_AI_CONFIG.time_limit_ms


def test_load_hard_config_rejects_unknown_fields(tmp_path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(
        '{"not_a_hard_field": 1}',
        encoding="utf-8",
    )

    try:
        load_hard_config(path, DEFAULT_HARD_AI_CONFIG)
    except ValueError as exc:
        assert "not_a_hard_field" in str(exc)
    else:
        raise AssertionError("Unknown fields must be rejected.")
