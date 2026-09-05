from dataclasses import replace
import gzip
import json
import random
from pathlib import Path
import sys


SRC_DIR = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SRC_DIR))

from gomoku.ai.hard_ai_config import DEFAULT_HARD_AI_CONFIG
from gomoku.ai.mcts import MCTSRootMove
from gomoku.ai.selfplay import (
    generate_selfplay_data,
    play_selfplay_game,
    sample_move,
    visit_distribution,
)
from gomoku.core.enums import Player


def _config(capacity: int):
    return replace(DEFAULT_HARD_AI_CONFIG, mcts_node_capacity=capacity)


def test_single_game_records_are_well_formed() -> None:
    records = play_selfplay_game(
        _config(20),
        seed=7,
        mcts_capacity=20,
        max_moves=8,
    )

    assert 1 <= len(records) <= 8
    outcomes = {record["outcome"] for record in records}
    assert outcomes <= {-1, 0, 1}
    for record in records:
        assert len(record["planes"]) == 2
        assert len(record["planes"][0]) == 15
        assert len(record["planes"][0][0]) == 15
        assert len(record["policy"]) == 225
        assert abs(sum(record["policy"]) - 1.0) < 1e-6
        assert record["player"] in (int(Player.BLACK), int(Player.WHITE))
        assert 0 <= record["move"][0] < 15
        assert 0 <= record["move"][1] < 15
    winner = next(
        (
            record["player"]
            for record in records
            if record["outcome"] == 1
        ),
        None,
    )
    for record in records:
        if winner is None:
            assert record["outcome"] == 0
        else:
            expected = 1 if record["player"] == winner else -1
            assert record["outcome"] == expected


def test_visit_distribution_sums_and_zeroes() -> None:
    root_moves = (
        MCTSRootMove((7, 7), 30, 0.6),
        MCTSRootMove((7, 8), 20, 0.4),
    )
    distribution = visit_distribution(root_moves, 15)

    assert abs(sum(distribution) - 1.0) < 1e-9
    assert distribution[7 * 15 + 7] == 0.6
    assert distribution[7 * 15 + 8] == 0.4
    assert distribution[0] == 0.0


def test_visit_distribution_uniform_when_no_visits() -> None:
    uniform = visit_distribution((), 15)

    assert abs(sum(uniform) - 1.0) < 1e-9
    assert abs(uniform[0] - 1.0 / 225) < 1e-12


def test_visit_distribution_mass_on_immediate_win() -> None:
    distribution = visit_distribution(
        (MCTSRootMove((3, 4), 0, 1.0),), 15
    )

    assert distribution[3 * 15 + 4] == 1.0
    assert sum(distribution) == 1.0


def test_sample_move_argmax_and_temperature() -> None:
    root_moves = (
        MCTSRootMove((7, 7), 30, 0.6),
        MCTSRootMove((0, 0), 10, 0.4),
    )
    rng = random.Random(1)

    assert sample_move(root_moves, 0.0, rng, 15) == (7, 7)

    rng = random.Random(42)
    picks = {
        sample_move(root_moves, 1.0, rng, 15)
        for _ in range(500)
    }
    assert picks <= {(7, 7), (0, 0)}
    assert (7, 7) in picks


def test_sample_move_falls_back_when_empty() -> None:
    rng = random.Random(0)

    assert sample_move((), 1.0, rng, 15, fallback=(7, 7)) == (7, 7)
    assert sample_move((), 1.0, rng, 15) is None


def test_different_seeds_play_different_games() -> None:
    first = play_selfplay_game(
        _config(20), seed=1, mcts_capacity=20, max_moves=10
    )
    second = play_selfplay_game(
        _config(20), seed=2, mcts_capacity=20, max_moves=10
    )

    assert [record["move"] for record in first] != [
        record["move"] for record in second
    ]


def test_generated_file_is_deterministic_and_resumable(tmp_path) -> None:
    output = tmp_path / "selfplay.jsonl.gz"
    args = dict(
        games=2,
        mcts_capacity=20,
        max_moves=8,
        seed=11,
        temperature_cutoff=4,
    )

    first_written = generate_selfplay_data(
        _config(20), output_path=output, **args
    )
    first_bytes = output.read_bytes()
    assert first_written > 0

    second_written = generate_selfplay_data(
        _config(20), output_path=tmp_path / "again.jsonl.gz", **args
    )
    assert second_written == first_written
    assert (tmp_path / "again.jsonl.gz").read_bytes() == first_bytes

    resumed = generate_selfplay_data(
        _config(20), output_path=output, start_index=2, **args
    )
    assert resumed > 0
    with gzip.open(output, "rt", encoding="utf-8") as handle:
        lines = [json.loads(line) for line in handle]
    assert len(lines) == first_written + resumed
    for record in lines:
        assert abs(sum(record["policy"]) - 1.0) < 1e-6
