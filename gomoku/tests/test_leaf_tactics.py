from dataclasses import replace
from pathlib import Path
import sys

import pytest


SRC_DIR = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SRC_DIR))

from gomoku.ai.hard_ai_config import DEFAULT_HARD_AI_CONFIG
from gomoku.ai.leaf_tactics import classify_leaf
from gomoku.ai.mcts import MCTS
from gomoku.ai.policy_value import HeuristicPolicyValueProvider
from gomoku.ai.search_position import SearchPosition
from gomoku.ai.zobrist import ZobristTable
from gomoku.core.board import Board
from gomoku.core.enums import Player


def make_board(stones) -> Board:
    board = Board()
    for row, col, owner in stones:
        board.place(row, col, Player(owner))
    return board


def make_position(board: Board, player: Player) -> SearchPosition:
    return SearchPosition.from_board(
        board,
        player,
        ZobristTable(board.size, DEFAULT_HARD_AI_CONFIG.zobrist_seed),
        max_candidate_radius=DEFAULT_HARD_AI_CONFIG.candidate_radius,
    )


class _CountingProvider(HeuristicPolicyValueProvider):
    def __init__(self, config) -> None:
        super().__init__(config)
        self.value_calls = 0

    def value(self, position, player, *, timeout_check=None):
        self.value_calls += 1
        return super().value(
            position, player, timeout_check=timeout_check
        )


def _make_mcts(config, provider) -> MCTS:
    return MCTS(config, provider, clock=lambda: 0.0)


# ------------------------------------------------------------- classifier


def test_classify_immediate_win() -> None:
    board = make_board(
        [(7, 4, 1), (7, 5, 1), (7, 6, 1), (7, 7, 1), (7, 8, 2), (8, 8, 2)]
    )
    position = make_position(board, Player.BLACK)
    tactics = classify_leaf(
        position, Player.BLACK, {(7, 3), (6, 6), (8, 8)}
    )
    assert tactics.immediate_win == (7, 3)
    assert tactics.opponent_win is None
    assert tactics.double_four is None


def test_classify_opponent_win_returns_block() -> None:
    board = make_board(
        [(7, 4, 1), (7, 5, 1), (7, 6, 1), (7, 7, 1), (7, 8, 2), (8, 8, 2)]
    )
    position = make_position(board, Player.WHITE)
    tactics = classify_leaf(
        position, Player.WHITE, {(7, 3), (6, 6), (7, 9)}
    )
    assert tactics.immediate_win is None
    assert tactics.opponent_win == (7, 3)
    assert tactics.double_four is None


def test_classify_double_four() -> None:
    board = make_board(
        [
            (7, 5, 1),
            (7, 6, 1),
            (7, 7, 1),
            (5, 8, 1),
            (6, 8, 1),
            (8, 8, 1),
            (3, 4, 2),
            (4, 4, 2),
        ]
    )
    position = make_position(board, Player.BLACK)
    tactics = classify_leaf(
        position, Player.BLACK, {(6, 6), (7, 8), (8, 9)}
    )
    assert tactics.immediate_win is None
    assert tactics.opponent_win is None
    assert tactics.double_four == (7, 8)


def test_classify_clean_position_is_empty() -> None:
    board = make_board([(7, 7, 1)])
    position = make_position(board, Player.WHITE)
    candidates = {
        (6, 6), (6, 7), (6, 8), (7, 6), (7, 8),
        (8, 6), (8, 7), (8, 8),
    }
    tactics = classify_leaf(position, Player.WHITE, candidates)
    assert tactics.immediate_win is None
    assert tactics.opponent_win is None
    assert tactics.double_four is None


# ------------------------------------------------------- MCTS integration


def test_mcts_blocks_open_four_within_tiny_capacity() -> None:
    # White to move; Black has a one-open-end four, so every non-blocking
    # White move loses to Black's forced completion at (7, 3). The search
    # needs enough simulations to revisit the block after the first sweep
    # of the candidate pool, but no more.
    board = make_board(
        [(7, 4, 1), (7, 5, 1), (7, 6, 1), (7, 7, 1), (7, 8, 2), (8, 8, 2)]
    )
    config = replace(DEFAULT_HARD_AI_CONFIG, mcts_node_capacity=100)
    mcts = _make_mcts(config, HeuristicPolicyValueProvider(config))
    result = mcts.search(
        board, Player.WHITE, time_budget_ms=1_000_000.0
    )
    assert result.simulations > 0
    assert result.move == (7, 3)
    assert board.is_empty(*result.move)


def test_mcts_forced_leaf_skips_provider_value() -> None:
    board = make_board(
        [(7, 4, 1), (7, 5, 1), (7, 6, 1), (7, 7, 1), (7, 8, 2), (8, 8, 2)]
    )
    config = replace(DEFAULT_HARD_AI_CONFIG, mcts_node_capacity=40)
    provider = _CountingProvider(config)
    mcts = _make_mcts(config, provider)
    result = mcts.search(
        board, Player.WHITE, time_budget_ms=1_000_000.0
    )
    assert result.simulations > 0
    # Non-blocking leaves get the forced 1.0 for Black without a provider
    # call; only the block leaf asks the provider.
    assert 0 < provider.value_calls < result.simulations

    # The forced winning cell joins the child's expansion priorities.
    root = mcts._reuse_subtree
    assert root is not None
    prioritized = [
        child.untried[0]
        for move, child in root.children.items()
        if move != (7, 3) and child.untried
    ]
    assert prioritized and all(
        top == (7, 3) for top in prioritized
    )


def test_mcts_disabled_leaf_tactics_always_uses_provider() -> None:
    board = make_board(
        [(7, 4, 1), (7, 5, 1), (7, 6, 1), (7, 7, 1), (7, 8, 2), (8, 8, 2)]
    )
    config = replace(
        DEFAULT_HARD_AI_CONFIG,
        mcts_node_capacity=40,
        mcts_leaf_tactics_enabled=False,
    )
    provider = _CountingProvider(config)
    mcts = _make_mcts(config, provider)
    result = mcts.search(
        board, Player.WHITE, time_budget_ms=1_000_000.0
    )
    assert result.simulations > 0
    assert provider.value_calls == result.simulations


def test_mcts_double_four_forces_leaf_value() -> None:
    # Black owns two threes crossing at (7, 8): playing there makes two
    # open fours, so every White response loses. The forced 1.0 leaves
    # must not cost a provider call.
    board = make_board(
        [
            (7, 5, 1),
            (7, 6, 1),
            (7, 7, 1),
            (5, 8, 1),
            (6, 8, 1),
            (8, 8, 1),
            (3, 4, 2),
            (4, 4, 2),
        ]
    )
    config = replace(DEFAULT_HARD_AI_CONFIG, mcts_node_capacity=40)
    provider = _CountingProvider(config)
    mcts = _make_mcts(config, provider)
    result = mcts.search(
        board, Player.WHITE, time_budget_ms=1_000_000.0
    )
    assert result.simulations > 0
    assert 0 < provider.value_calls < result.simulations

    disabled_config = replace(
        DEFAULT_HARD_AI_CONFIG,
        mcts_node_capacity=40,
        mcts_leaf_tactics_enabled=False,
    )
    disabled_provider = _CountingProvider(disabled_config)
    disabled_mcts = _make_mcts(disabled_config, disabled_provider)
    disabled = disabled_mcts.search(
        board, Player.WHITE, time_budget_ms=1_000_000.0
    )
    assert disabled_provider.value_calls == disabled.simulations


def test_mcts_opponent_win_prioritizes_block() -> None:
    # Black plays (7, 4) making a one-open-end four; the child's (White's)
    # expansion must surface the mandatory block (7, 8) first.
    board = make_board(
        [(7, 5, 1), (7, 6, 1), (7, 7, 1), (7, 3, 2), (3, 4, 2), (4, 4, 2)]
    )
    config = replace(DEFAULT_HARD_AI_CONFIG, mcts_node_capacity=20)
    mcts = _make_mcts(config, HeuristicPolicyValueProvider(config))
    mcts.search(
        board,
        Player.BLACK,
        time_budget_ms=1_000_000.0,
        priority_moves=((7, 4),),
    )
    root = mcts._reuse_subtree
    assert root is not None
    child = root.children.get((7, 4))
    assert child is not None
    assert child.untried and child.untried[0] == (7, 8)
