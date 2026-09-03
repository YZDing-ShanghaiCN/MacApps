from dataclasses import replace
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
    class DeterministicClock:
        def __init__(self, limit: int) -> None:
            self.calls = 0
            self.limit = limit

        def __call__(self) -> float:
            self.calls += 1
            return 1e12 if self.calls > self.limit else 0.0

    board = make_board([(7, 7, 1), (8, 8, 2), (6, 6, 1)])

    def run():
        return MCTS(
            DEFAULT_HARD_AI_CONFIG,
            HeuristicPolicyValueProvider(DEFAULT_HARD_AI_CONFIG),
            clock=DeterministicClock(8000),
        ).search(board, Player.WHITE, time_budget_ms=200)

    first = run()
    second = run()
    assert first.move == second.move
    assert first.simulations == second.simulations
    assert first.root_visits == second.root_visits
    assert first.timed_out == second.timed_out


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


def test_node_capacity_gives_clean_exit_and_safe_reuse() -> None:
    config = replace(DEFAULT_HARD_AI_CONFIG, mcts_node_capacity=40)
    mcts = MCTS(
        config,
        HeuristicPolicyValueProvider(config),
        clock=lambda: 0.0,
    )
    board = make_board([(7, 7, 1), (8, 8, 2)])
    first = mcts.search(board, Player.WHITE, time_budget_ms=200)
    assert first.timed_out is False
    assert first.simulations == 40
    assert first.move is not None
    assert board.is_empty(*first.move)

    # Same position again: the clean completion allows root reuse. Simulating
    # through the reused subtree exercises the re-linked parent chain in the
    # backup loop (stale parents would crash with an AttributeError).
    second = mcts.search(board, Player.WHITE, time_budget_ms=200)
    assert second.timed_out is False
    assert second.simulations == 40
    assert second.root_visits == second.simulations
    assert second.move is not None
    assert board.is_empty(*second.move)


def test_deadline_checked_during_policy_expansion() -> None:
    class CountingClock:
        def __init__(self) -> None:
            self.calls = 0

        def __call__(self) -> float:
            self.calls += 1
            return 1e12 if self.calls > 5 else 0.0

    mcts = MCTS(
        DEFAULT_HARD_AI_CONFIG,
        HeuristicPolicyValueProvider(DEFAULT_HARD_AI_CONFIG),
        clock=CountingClock(),
    )
    board = make_board([(7, 7, 1), (8, 8, 2)])
    result = mcts.search(board, Player.WHITE, time_budget_ms=200)
    assert result.timed_out is True
    assert result.simulations == 0
    assert result.move is not None
    assert board.is_empty(*result.move)


def test_provider_receives_timeout_callback() -> None:
    class RecordingProvider(HeuristicPolicyValueProvider):
        def __init__(self, config) -> None:
            super().__init__(config)
            self.policy_callback_seen = False
            self.value_callback_seen = False

        def policy(
            self, position, player, legal_moves, *, timeout_check=None
        ):
            if timeout_check is not None:
                self.policy_callback_seen = True
            return super().policy(
                position, player, legal_moves, timeout_check=timeout_check
            )

        def value(self, position, player, *, timeout_check=None):
            if timeout_check is not None:
                self.value_callback_seen = True
            return super().value(
                position, player, timeout_check=timeout_check
            )

    provider = RecordingProvider(DEFAULT_HARD_AI_CONFIG)
    mcts = MCTS(DEFAULT_HARD_AI_CONFIG, provider)
    board = make_board([(7, 7, 1), (8, 8, 2)])
    result = mcts.search(board, Player.WHITE, time_budget_ms=200)
    assert result.simulations > 0
    assert provider.policy_callback_seen
    assert provider.value_callback_seen
