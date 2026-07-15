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


def test_simple_ai_blocks_an_isolated_opponent_stone_from_its_neighbor_ring() -> None:
    board = Board()
    board.place(7, 7, Player.BLACK)

    move = SimpleAI().choose_move(board, Player.WHITE, (7, 7))

    assert move == (7, 6)


def test_simple_ai_does_not_use_random_fallback_for_an_isolated_opponent_stone(
    monkeypatch,
) -> None:
    board = Board()
    board.place(7, 7, Player.BLACK)

    monkeypatch.setattr(
        "gomoku.ai.simple_ai.random.choice",
        lambda _moves: (_ for _ in ()).throw(AssertionError("unexpected random move")),
    )

    move = SimpleAI(Player.WHITE).choose_move(board, last_opponent_move=(7, 7))

    assert move == (7, 6)


def test_simple_ai_grows_an_isolated_own_stone_before_blocking_an_opponent_one() -> None:
    board = Board()
    board.place(7, 7, Player.WHITE)
    board.place(10, 10, Player.BLACK)

    assert SimpleAI(Player.WHITE).choose_move(board) == (7, 6)


def test_simple_ai_prefers_a_single_neighbor_closer_to_the_board_center() -> None:
    board = Board()
    board.place(4, 4, Player.BLACK)

    assert SimpleAI(Player.WHITE).choose_move(board) == (5, 5)


def test_simple_ai_ignores_non_isolated_stones_for_neighbor_ring_strategy() -> None:
    board = Board()
    board.place(7, 7, Player.WHITE)
    board.place(7, 8, Player.WHITE)

    assert SimpleAI(Player.WHITE)._find_isolated_stone_neighbor(board, Player.WHITE) is None


def test_simple_ai_attacks_own_three_before_lower_defense() -> None:
    board = Board()
    for col in range(5, 8):
        board.place(5, col, Player.WHITE)
    for col in range(5, 8):
        board.place(8, col, Player.BLACK)

    move = SimpleAI(Player.WHITE).choose_move(
        board,
        last_opponent_move=(8, 7),
    )

    assert move in {(5, 4), (5, 8)}


def test_simple_ai_prefers_an_open_own_three_over_a_single_ended_one() -> None:
    board = Board()
    board.place(3, 4, Player.BLACK)
    for col in range(5, 8):
        board.place(3, col, Player.WHITE)
        board.place(7, col, Player.WHITE)

    assert SimpleAI(Player.WHITE).choose_move(board) == (7, 4)


def test_simple_ai_prefers_an_open_opponent_three_over_a_single_ended_one(
    monkeypatch,
) -> None:
    board = Board()
    board.place(3, 4, Player.WHITE)
    for col in range(5, 8):
        board.place(3, col, Player.BLACK)
        board.place(7, col, Player.BLACK)

    monkeypatch.setattr(
        "gomoku.ai.simple_ai.random.choice",
        lambda moves: moves[-1],
    )

    assert SimpleAI(Player.WHITE).choose_move(board) == (7, 8)


def test_simple_ai_prefers_a_move_that_extends_two_own_threes() -> None:
    board = Board()
    for col in range(4, 7):
        board.place(7, col, Player.WHITE)
    for row in range(4, 7):
        board.place(row, 7, Player.WHITE)

    assert SimpleAI(Player.WHITE).choose_move(board) == (7, 7)


def test_simple_ai_prefers_a_move_that_blocks_two_opponent_threes() -> None:
    board = Board()
    for col in range(4, 7):
        board.place(7, col, Player.BLACK)
    for row in range(4, 7):
        board.place(row, 7, Player.BLACK)

    assert SimpleAI(Player.WHITE).choose_move(board) == (7, 7)


def test_simple_ai_blocks_immediate_loss_before_attacking_three() -> None:
    board = Board()
    for col in range(5, 8):
        board.place(5, col, Player.WHITE)
    for col in range(5, 9):
        board.place(8, col, Player.BLACK)

    move = SimpleAI(Player.WHITE).choose_move(
        board,
        last_opponent_move=(8, 8),
    )

    assert move in {(8, 4), (8, 9)}


def test_simple_ai_wins_own_four_before_blocking_opponent_four() -> None:
    board = Board()
    for col in range(5, 9):
        board.place(5, col, Player.WHITE)
        board.place(8, col, Player.BLACK)

    move = SimpleAI(Player.WHITE).choose_move(board)

    assert move in {(5, 4), (5, 9)}


def test_simple_ai_blocks_the_only_open_end_of_opponent_four() -> None:
    board = Board()
    board.place(7, 4, Player.WHITE)
    for col in range(5, 9):
        board.place(7, col, Player.BLACK)

    assert SimpleAI(Player.WHITE).choose_move(board) == (7, 9)


def test_simple_ai_extends_own_two_before_blocking_opponent_two() -> None:
    board = Board()
    for col in range(5, 7):
        board.place(5, col, Player.WHITE)
        board.place(8, col, Player.BLACK)

    move = SimpleAI(Player.WHITE).choose_move(board)

    assert move in {(5, 4), (5, 7)}


def test_simple_ai_skips_a_two_sided_blocked_line() -> None:
    board = Board()
    board.place(7, 4, Player.WHITE)
    for col in range(5, 8):
        board.place(7, col, Player.BLACK)
    board.place(7, 8, Player.WHITE)
    board.place(5, 5, Player.WHITE)
    board.place(5, 6, Player.WHITE)

    move = SimpleAI(Player.WHITE).choose_move(board)

    assert move in {(5, 4), (5, 7)}


def test_simple_ai_does_not_treat_a_gapped_shape_as_a_three() -> None:
    board = Board()
    for col in (4, 6, 7):
        board.place(7, col, Player.BLACK)
    board.place(5, 5, Player.WHITE)
    board.place(5, 6, Player.WHITE)

    move = SimpleAI(Player.WHITE).choose_move(board)

    assert move in {(5, 4), (5, 7)}


def test_simple_ai_randomly_blocks_an_end_of_opponent_three(monkeypatch) -> None:
    board = Board()
    for col in range(5, 8):
        board.place(7, col, Player.BLACK)

    monkeypatch.setattr(
        "gomoku.ai.simple_ai.random.choice",
        lambda moves: moves[-1],
    )

    assert SimpleAI(Player.WHITE).choose_move(board) == (7, 8)


def test_simple_ai_randomly_blocks_an_end_of_opponent_two(monkeypatch) -> None:
    board = Board()
    for col in range(5, 7):
        board.place(7, col, Player.BLACK)

    monkeypatch.setattr(
        "gomoku.ai.simple_ai.random.choice",
        lambda moves: moves[-1],
    )

    assert SimpleAI(Player.WHITE).choose_move(board) == (7, 7)


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
