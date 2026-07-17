from pathlib import Path
import sys

import pytest


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from gomoku.ai.normal_ai import NormalAI
from gomoku.core.board import Board
from gomoku.core.enums import Player


@pytest.mark.parametrize(
    ("stones", "player", "expected"),
    [
        (
            [(7, col, Player.WHITE) for col in range(4, 8)],
            Player.WHITE,
            {(7, 3), (7, 8)},
        ),
        (
            [(row, 7, Player.BLACK) for row in range(4, 8)],
            Player.WHITE,
            {(3, 7), (8, 7)},
        ),
        (
            [(index, index, Player.BLACK) for index in range(4, 8)],
            Player.WHITE,
            {(3, 3), (8, 8)},
        ),
        (
            [(index, 14 - index, Player.BLACK) for index in range(4, 8)],
            Player.WHITE,
            {(3, 11), (8, 6)},
        ),
        (
            [(7, col, Player.BLACK) for col in (4, 5, 7, 8)],
            Player.WHITE,
            {(7, 6)},
        ),
    ],
)
def test_fixed_immediate_tactical_positions(stones, player, expected) -> None:
    board = Board()
    for row, col, stone_player in stones:
        board.place(row, col, stone_player)
    assert NormalAI(player).choose_move(board) in expected


def test_own_win_takes_priority_over_blocking_opponent() -> None:
    board = Board()
    for col in range(4, 8):
        board.place(5, col, Player.WHITE)
        board.place(9, col, Player.BLACK)
    assert NormalAI(Player.WHITE).choose_move(board) in {(5, 3), (5, 8)}
