from pathlib import Path
import sys


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from gomoku.ai.simple_ai import RandomAI, SimpleAI
from gomoku.core.board import Board
from gomoku.core.enums import Player


def test_simple_ai_blocks_horizontal_four() -> None:
    board = Board()
    for col in range(4, 8):
        board.place(7, col, Player.BLACK)

    move = SimpleAI().choose_move(board, Player.WHITE, (7, 7))

    assert move in {(7, 3), (7, 8)}


def test_simple_ai_blocks_vertical_three() -> None:
    board = Board()
    for row in range(5, 8):
        board.place(row, 7, Player.BLACK)

    move = SimpleAI().choose_move(board, Player.WHITE, (7, 7))

    assert move in {(4, 7), (8, 7)}


def test_simple_ai_blocks_diagonal_two() -> None:
    board = Board()
    board.place(7, 7, Player.BLACK)
    board.place(8, 8, Player.BLACK)

    move = SimpleAI().choose_move(board, Player.WHITE, (8, 8))

    assert move in {(6, 6), (9, 9)}


def test_simple_ai_random_move_stays_near_last_opponent_move() -> None:
    board = Board()
    board.place(7, 7, Player.BLACK)

    move = SimpleAI().choose_move(board, Player.WHITE, (7, 7))

    assert move is not None
    row, col = move
    assert 3 <= row <= 11
    assert 3 <= col <= 11
    assert board.is_empty(row, col)


def test_simple_ai_handles_invalid_last_opponent_move() -> None:
    board = Board()
    board.place(7, 7, Player.BLACK)

    move = SimpleAI().choose_move(board, Player.WHITE, (20, 20))

    assert move is not None
    assert board.is_empty(*move)


def test_simple_ai_falls_back_when_nearby_area_is_full() -> None:
    board = Board()
    for row in range(3, 12):
        for col in range(3, 12):
            board.place(row, col, Player.BLACK)

    move = SimpleAI().choose_move(board, Player.WHITE, (7, 7))

    assert move is not None
    row, col = move
    assert not (3 <= row <= 11 and 3 <= col <= 11)
    assert board.is_empty(row, col)


def test_simple_ai_returns_none_when_board_is_full() -> None:
    board = Board()
    for row in range(board.size):
        for col in range(board.size):
            board.place(row, col, Player.BLACK)

    assert SimpleAI().choose_move(board, Player.WHITE, (7, 7)) is None


def test_random_ai_still_returns_legal_move() -> None:
    board = Board()
    board.place(7, 7, Player.BLACK)

    move = RandomAI().choose_move(board)

    assert move is not None
    assert board.is_empty(*move)
