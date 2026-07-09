from pathlib import Path
import sys

import pytest


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from gomoku.core.board import Board
from gomoku.core.enums import Player
from gomoku.core.exceptions import InvalidMoveError


def test_board_initially_empty() -> None:
    board = Board()

    assert board.size == 15
    assert all(cell == Player.EMPTY for row in board.grid for cell in row)


def test_is_inside_detects_bounds() -> None:
    board = Board()

    assert board.is_inside(0, 0)
    assert board.is_inside(14, 14)
    assert not board.is_inside(-1, 0)
    assert not board.is_inside(0, 15)


def test_cannot_place_on_occupied_cell() -> None:
    board = Board()
    board.place(7, 7, Player.BLACK)

    with pytest.raises(InvalidMoveError):
        board.place(7, 7, Player.WHITE)


def test_reset_clears_board() -> None:
    board = Board()
    board.place(3, 4, Player.BLACK)

    board.reset()

    assert all(cell == Player.EMPTY for row in board.grid for cell in row)
