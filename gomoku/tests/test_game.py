from pathlib import Path
import sys

import pytest


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from gomoku.core.enums import Player
from gomoku.core.exceptions import InvalidMoveError
from gomoku.core.game import GomokuGame


def test_black_moves_first() -> None:
    game = GomokuGame()

    assert game.current_player == Player.BLACK


def test_valid_move_switches_player() -> None:
    game = GomokuGame()

    game.make_move(7, 7)

    assert game.board.grid[7][7] == Player.BLACK
    assert game.current_player == Player.WHITE


def test_invalid_move_raises_error() -> None:
    game = GomokuGame()
    game.make_move(7, 7)

    with pytest.raises(InvalidMoveError):
        game.make_move(7, 7)


def test_game_over_after_win() -> None:
    game = GomokuGame()
    moves = [
        (0, 0),
        (1, 0),
        (0, 1),
        (1, 1),
        (0, 2),
        (1, 2),
        (0, 3),
        (1, 3),
        (0, 4),
    ]

    for row, col in moves:
        game.make_move(row, col)

    assert game.game_over
    assert game.winner == Player.BLACK


def test_reset_restores_initial_state() -> None:
    game = GomokuGame()
    game.make_move(7, 7)

    game.reset()

    assert game.current_player == Player.BLACK
    assert game.winner is None
    assert not game.game_over
    assert game.move_history == []
    assert all(cell == Player.EMPTY for row in game.board.grid for cell in row)


def test_undo_reverts_one_move() -> None:
    game = GomokuGame()
    game.make_move(7, 7)

    undone = game.undo()

    assert undone
    assert game.board.grid[7][7] == Player.EMPTY
    assert game.current_player == Player.BLACK
    assert game.move_history == []
