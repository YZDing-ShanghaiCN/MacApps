from pathlib import Path
import sys


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from gomoku.core.board import Board
from gomoku.core.enums import Player
from gomoku.core.rules import check_win, find_winning_line


def test_horizontal_five_wins() -> None:
    board = Board()
    for col in range(5):
        board.place(7, col, Player.BLACK)

    assert check_win(board, 7, 4, Player.BLACK)


def test_vertical_five_wins() -> None:
    board = Board()
    for row in range(5):
        board.place(row, 7, Player.BLACK)

    assert check_win(board, 4, 7, Player.BLACK)


def test_main_diagonal_five_wins() -> None:
    board = Board()
    for index in range(5):
        board.place(index, index, Player.BLACK)

    assert check_win(board, 4, 4, Player.BLACK)


def test_anti_diagonal_five_wins() -> None:
    board = Board()
    for index in range(5):
        board.place(4 - index, index, Player.BLACK)

    assert check_win(board, 0, 4, Player.BLACK)


def test_less_than_five_does_not_win() -> None:
    board = Board()
    for col in range(4):
        board.place(7, col, Player.BLACK)

    assert not check_win(board, 7, 3, Player.BLACK)


def test_find_winning_line_returns_all_connected_winning_stones() -> None:
    board = Board()
    for col in range(3, 9):
        board.place(7, col, Player.BLACK)

    assert find_winning_line(board, 7, 8, Player.BLACK) == tuple(
        (7, col) for col in range(3, 9)
    )
