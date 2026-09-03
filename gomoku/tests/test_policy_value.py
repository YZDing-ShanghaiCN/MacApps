from pathlib import Path
import sys

import pytest


SRC_DIR = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SRC_DIR))

from gomoku.ai.hard_ai_config import DEFAULT_HARD_AI_CONFIG
from gomoku.ai.policy_value import HeuristicPolicyValueProvider
from gomoku.ai.search_position import SearchPosition
from gomoku.ai.zobrist import ZobristTable
from gomoku.core.board import Board
from gomoku.core.enums import Player


def make_position(stones, player: Player) -> SearchPosition:
    board = Board()
    for row, col, owner in stones:
        board.place(row, col, Player(owner))
    return SearchPosition.from_board(
        board,
        player,
        ZobristTable(board.size, DEFAULT_HARD_AI_CONFIG.zobrist_seed),
        max_candidate_radius=DEFAULT_HARD_AI_CONFIG.candidate_radius,
    )


def make_provider():
    return HeuristicPolicyValueProvider(DEFAULT_HARD_AI_CONFIG)


def test_policy_sums_to_one_and_is_positive() -> None:
    position = make_position([(7, 7, 1)], Player.WHITE)
    pool = sorted(position.nearby_empty_moves(2))
    assert pool
    policy = make_provider().policy(position, Player.WHITE, pool)
    assert set(policy) == set(pool)
    assert all(0.0 < p <= 1.0 for p in policy.values())
    assert abs(sum(policy.values()) - 1.0) < 1e-9


def test_policy_prefers_four_completing_cell() -> None:
    position = make_position(
        [(7, 4, 1), (7, 5, 1), (7, 6, 1)], Player.BLACK
    )
    policy = make_provider().policy(
        position, Player.BLACK, [(7, 3), (0, 0)]
    )
    assert policy[(7, 3)] > policy[(0, 0)] * 10


def test_policy_deterministic_and_board_unchanged() -> None:
    position = make_position([(7, 7, 1), (8, 8, 2)], Player.WHITE)
    before = position.to_list()
    pool = sorted(position.nearby_empty_moves(2))
    first = make_provider().policy(position, Player.WHITE, pool)
    second = make_provider().policy(position, Player.WHITE, pool)
    assert first == second
    assert position.to_list() == before


def test_policy_empty_pool_returns_empty() -> None:
    position = make_position([], Player.BLACK)
    assert make_provider().policy(position, Player.BLACK, []) == {}


def test_value_in_unit_interval_and_deterministic() -> None:
    position = make_position([(7, 7, 1)], Player.WHITE)
    provider = make_provider()
    first = provider.value(position, Player.WHITE)
    second = provider.value(position, Player.WHITE)
    assert 0.0 < first < 1.0
    assert first == second


def test_value_near_one_with_live_open_four() -> None:
    position = make_position(
        [(7, 4, 1), (7, 5, 1), (7, 6, 1), (7, 7, 1)], Player.BLACK
    )
    assert make_provider().value(position, Player.BLACK) > 0.9


def test_value_full_board_is_half() -> None:
    board = Board()
    for row in range(board.size):
        for col in range(board.size):
            board.place(row, col, Player.BLACK if (row + col) % 2 else Player.WHITE)
    position = SearchPosition.from_board(
        board,
        Player.BLACK,
        ZobristTable(board.size, DEFAULT_HARD_AI_CONFIG.zobrist_seed),
    )
    assert make_provider().value(position, Player.BLACK) == 0.5
