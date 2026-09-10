from dataclasses import replace
from pathlib import Path
import sys


SRC_DIR = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SRC_DIR))

from gomoku.ai.hard_arena import compare_hard_configs  # noqa: E402
from gomoku.ai.hard_ai_config import DEFAULT_HARD_AI_CONFIG  # noqa: E402
from gomoku.ai.opening_generator import generate_openings  # noqa: E402
from gomoku.ai.promotion import should_promote  # noqa: E402


def _report(equivalent_wins: float, games: int) -> dict:
    from gomoku.ai.arena import wilson_interval

    confidence = wilson_interval(equivalent_wins, games)
    score = equivalent_wins / games
    return {
        "score_rate": {"A": score, "B": 1.0 - score},
        "score_confidence_95": {
            "A": confidence,
            "B": (1.0 - confidence[1], 1.0 - confidence[0]),
        },
    }


def test_promote_when_wilson_interval_fully_above_half() -> None:
    assert should_promote(_report(9.0, 10)) is True
    # 8/10: point score 0.8 but the Wilson 95% lower bound is still below
    # 0.5, so the conservative CI rule must withhold promotion.
    assert should_promote(_report(8.0, 10)) is False


def test_no_promotion_when_interval_straddles_half() -> None:
    assert should_promote(_report(6.0, 10)) is False
    assert should_promote(_report(5.0, 10)) is False


def test_point_score_above_half_is_not_sufficient() -> None:
    # 4 wins / 6 games: raw score 0.667 but the 95% CI lower bound is 0.33,
    # so the candidate must NOT be promoted on point score alone.
    report = _report(4.0, 6)
    assert report["score_rate"]["A"] > 0.5
    assert report["score_confidence_95"]["A"][0] < 0.5
    assert should_promote(report) is False


def test_generated_opening_match_plays_both_colors_with_metadata() -> None:
    config = replace(DEFAULT_HARD_AI_CONFIG, mcts_node_capacity=30)
    openings = generate_openings(seed=7, count=2, length=2)
    summary = compare_hard_configs(
        config,
        config,
        mcts_capacity=30,
        max_moves=4,
        openings=openings,
        opening_mode="generated",
        opening_seed=7,
        opening_length_min=2,
        opening_length_max=2,
    )

    assert summary.games == 4
    assert summary.opening_mode == "generated"
    assert summary.opening_seed == 7
    assert summary.opening_count == 2
    assert summary.opening_length_min == 2
    assert summary.openings == openings
    first, second = summary.game_records[0], summary.game_records[1]
    assert first.opening == second.opening == openings[0]
    assert first.black_label == "A" and first.white_label == "B"
    assert second.black_label == "B" and second.white_label == "A"
    third, fourth = summary.game_records[2], summary.game_records[3]
    assert third.opening == fourth.opening == openings[1]


def test_invalid_opening_is_rejected_by_arena() -> None:
    config = replace(DEFAULT_HARD_AI_CONFIG, mcts_node_capacity=30)
    from gomoku.core.enums import Player

    terminal = (
        (7, 3, Player.BLACK),
        (7, 8, Player.WHITE),
        (7, 4, Player.BLACK),
        (7, 9, Player.WHITE),
        (7, 5, Player.BLACK),
        (7, 10, Player.WHITE),
        (7, 6, Player.BLACK),
        (7, 11, Player.WHITE),
        (7, 7, Player.BLACK),
    )
    try:
        compare_hard_configs(
            config,
            config,
            mcts_capacity=30,
            max_moves=4,
            openings=(terminal,),
        )
    except ValueError as exc:
        assert "Invalid opening" in str(exc)
    else:
        raise AssertionError("Terminal openings must be rejected.")
