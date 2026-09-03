from pathlib import Path
import sys
import threading

import pytest


SRC_DIR = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SRC_DIR))

from gomoku.ai.hard_ai_config import DEFAULT_HARD_AI_CONFIG
from gomoku.ai.mcts import MCTS
from gomoku.ai.policy_value import HeuristicPolicyValueProvider
from gomoku.core.board import Board
from gomoku.core.enums import Player


def make_board(stones) -> Board:
    board = Board()
    for row, col, owner in stones:
        board.place(row, col, Player(owner))
    return board


def make_mcts() -> MCTS:
    return MCTS(
        DEFAULT_HARD_AI_CONFIG,
        HeuristicPolicyValueProvider(DEFAULT_HARD_AI_CONFIG),
    )


def test_empty_board_returns_center() -> None:
    result = make_mcts().search(
        Board(), Player.BLACK, time_budget_ms=200
    )
    assert result.move == (7, 7)
    assert result.simulations == 0
    assert result.timed_out is False


def test_near_empty_board_runs_simulations() -> None:
    board = make_board([(7, 7, 1)])
    result = make_mcts().search(
        board, Player.WHITE, time_budget_ms=200
    )
    assert result.simulations > 0
    assert result.root_visits == result.simulations
    assert result.move is not None
    assert board.is_empty(*result.move)


def test_prefers_immediate_win() -> None:
    board = make_board([(7, 4, 1), (7, 5, 1), (7, 6, 1), (7, 7, 1)])
    result = make_mcts().search(
        board, Player.BLACK, time_budget_ms=300
    )
    assert result.move in {(7, 3), (7, 8)}
    assert board.to_list() == make_board(
        [(7, 4, 1), (7, 5, 1), (7, 6, 1), (7, 7, 1)]
    ).to_list()


def test_deterministic_across_instances() -> None:
    board = make_board([(7, 7, 1), (8, 8, 2), (6, 6, 1)])
    first = make_mcts().search(board, Player.WHITE, time_budget_ms=200)
    second = make_mcts().search(board, Player.WHITE, time_budget_ms=200)
    assert first.move == second.move
    assert first.simulations == second.simulations
    assert first.root_visits == second.root_visits


def test_respects_budget_and_never_exceeds() -> None:
    board = make_board([(7, 7, 1), (8, 8, 2)])
    result = make_mcts().search(board, Player.WHITE, time_budget_ms=100)
    assert result.elapsed_ms < 100 + 150
    assert result.move is not None
    assert board.is_empty(*result.move)


def test_pre_set_cancel_still_returns_legal_move() -> None:
    board = make_board([(7, 7, 1)])
    cancel_event = threading.Event()
    cancel_event.set()
    result = make_mcts().search(
        board,
        Player.WHITE,
        time_budget_ms=200,
        cancel_event=cancel_event,
    )
    assert result.simulations == 0
    assert result.timed_out
    assert result.move is not None
    assert board.is_empty(*result.move)


def test_full_board_returns_none() -> None:
    board = Board()
    for row in range(board.size):
        for col in range(board.size):
            board.place(
                row, col, Player.BLACK if (row + col) % 2 else Player.WHITE
            )
    result = make_mcts().search(board, Player.BLACK, time_budget_ms=100)
    assert result.move is None


def test_root_reuse_is_safe_and_legal() -> None:
    mcts = make_mcts()
    board = make_board([(7, 7, 1), (8, 8, 2)])
    first = mcts.search(board, Player.WHITE, time_budget_ms=100)
    second = mcts.search(board, Player.WHITE, time_budget_ms=100)
    assert second.move is not None
    assert board.is_empty(*second.move)
    changed = make_board([(7, 7, 1), (8, 8, 2), (9, 9, 1)])
    third = mcts.search(changed, Player.WHITE, time_budget_ms=100)
    assert third.move is not None
    assert changed.is_empty(*third.move)
    assert first.move is not None


def test_priority_moves_get_explored() -> None:
    board = make_board([(7, 7, 1)])
    result = make_mcts().search(
        board,
        Player.WHITE,
        time_budget_ms=200,
        priority_moves=((7, 8), (6, 8)),
    )
    assert result.move is not None
    assert result.root_visits > 0
    visited = {item.move for item in result.root_moves}
    assert (7, 8) in visited or (6, 8) in visited
