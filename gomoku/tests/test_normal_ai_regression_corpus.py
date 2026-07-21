from dataclasses import replace
import json
from pathlib import Path
import sys

import pytest


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from gomoku.ai.normal_ai import NormalAI
from gomoku.ai.normal_ai_config import DEFAULT_NORMAL_AI_CONFIG
from gomoku.core.board import Board
from gomoku.core.enums import Player


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "normal_ai_positions.json"
POSITIONS = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
TEST_CONFIG = replace(
    DEFAULT_NORMAL_AI_CONFIG,
    time_limit_ms=10_000,
    max_depth=2,
    vcf_time_fraction=0.5,
    defensive_vcf_time_fraction=0.5,
)


@pytest.mark.parametrize("case", POSITIONS, ids=lambda case: case["name"])
def test_curated_normal_ai_regression_position(case) -> None:
    board = Board()
    for row, col, player in case["stones"]:
        board.place(row, col, Player(player))
    before = board.to_list()

    move = NormalAI(Player(case["player"]), config=TEST_CONFIG).choose_move(board)

    assert move in {tuple(expected) for expected in case["expected"]}
    assert board.to_list() == before


def test_unique_tactical_move_is_rotation_invariant() -> None:
    stones = [(7, 4, Player.BLACK), (7, 5, Player.BLACK), (7, 7, Player.BLACK), (7, 8, Player.BLACK)]
    expected = (7, 6)
    for rotations in range(4):
        board = Board()
        transformed_stones = [
            (*_rotate(row, col, rotations), player)
            for row, col, player in stones
        ]
        for row, col, player in transformed_stones:
            board.place(row, col, player)
        transformed_expected = _rotate(*expected, rotations)

        assert NormalAI(Player.WHITE, config=TEST_CONFIG).choose_move(board) == (
            transformed_expected
        )


def test_unique_tactical_move_is_color_symmetric() -> None:
    for attacker, defender in (
        (Player.BLACK, Player.WHITE),
        (Player.WHITE, Player.BLACK),
    ):
        board = Board()
        for col in (4, 5, 7, 8):
            board.place(7, col, attacker)
        assert NormalAI(defender, config=TEST_CONFIG).choose_move(board) == (7, 6)


def _rotate(row: int, col: int, turns: int) -> tuple[int, int]:
    for _ in range(turns):
        row, col = col, 14 - row
    return row, col
