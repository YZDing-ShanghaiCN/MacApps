from pathlib import Path
import sys


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from gomoku.ai.search_position import SearchPosition
from gomoku.ai.zobrist import ZobristTable
from gomoku.core.board import Board
from gomoku.core.enums import Player


def test_search_position_is_independent_and_undo_restores_everything() -> None:
    board = Board()
    board.place(7, 7, Player.BLACK)
    original = board.to_list()
    position = SearchPosition.from_board(
        board,
        Player.WHITE,
        ZobristTable(board.size, 12345),
    )
    original_hash = position.hash_key

    position.make_move(7, 8)
    position.make_move(6, 8)

    assert board.to_list() == original
    assert position.hash_key == position.recompute_hash()

    position.undo_move()
    position.undo_move()

    assert position.grid == original
    assert position.current_player == Player.WHITE
    assert position.hash_key == original_hash
    assert position.hash_key == position.recompute_hash()
    assert position.move_stack == []


def test_fixed_zobrist_seed_is_reproducible() -> None:
    board = Board()
    board.place(2, 3, Player.BLACK)
    first = SearchPosition.from_board(board, Player.WHITE, ZobristTable(15, 99))
    second = SearchPosition.from_board(board, Player.WHITE, ZobristTable(15, 99))

    assert first.hash_key == second.hash_key
    assert first.zobrist.side_to_move_key == second.zobrist.side_to_move_key
