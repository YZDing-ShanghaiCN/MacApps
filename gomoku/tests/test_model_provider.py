from dataclasses import replace
from pathlib import Path
import sys


SRC_DIR = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SRC_DIR))

import pytest

torch = pytest.importorskip("torch")

from gomoku.ai.hard_ai import HardAI
from gomoku.ai.hard_ai_config import DEFAULT_HARD_AI_CONFIG
from gomoku.ai.model import GomokuNet, save_model
from gomoku.ai.model_provider import ModelPolicyValueProvider
from gomoku.ai.search_position import SearchPosition
from gomoku.ai.zobrist import ZobristTable
from gomoku.core.board import Board
from gomoku.core.enums import Player
from gomoku.core.rules import get_valid_moves


def _tiny_model(tmp_path) -> Path:
    path = tmp_path / "tiny.pt"
    save_model(GomokuNet(size=15, blocks=1, channels=4), path)
    return path


def _position(board: Board, player: Player) -> SearchPosition:
    return SearchPosition.from_board(
        board,
        player,
        ZobristTable(board.size, DEFAULT_HARD_AI_CONFIG.zobrist_seed),
        max_candidate_radius=DEFAULT_HARD_AI_CONFIG.candidate_radius,
    )


def _provider(tmp_path) -> ModelPolicyValueProvider:
    return ModelPolicyValueProvider(
        DEFAULT_HARD_AI_CONFIG, str(_tiny_model(tmp_path))
    )


def test_policy_sums_to_one_over_legal_moves(tmp_path) -> None:
    board = Board(15)
    board.place(7, 7, Player.BLACK)
    board.place(7, 8, Player.WHITE)
    position = _position(board, Player.BLACK)
    legal = get_valid_moves(board)
    provider = _provider(tmp_path)

    policy = provider.policy(position, Player.BLACK, legal)

    assert set(policy) == set(legal)
    assert abs(sum(policy.values()) - 1.0) < 1e-6
    assert all(0.0 < probability <= 1.0 for probability in policy.values())


def test_policy_is_deterministic(tmp_path) -> None:
    board = Board(15)
    board.place(7, 7, Player.BLACK)
    position = _position(board, Player.BLACK)
    legal = get_valid_moves(board)
    provider = _provider(tmp_path)

    first = provider.policy(position, Player.BLACK, legal)
    second = provider.policy(position, Player.BLACK, legal)

    assert first == second


def test_timeout_check_is_invoked_and_honored(tmp_path) -> None:
    board = Board(15)
    board.place(7, 7, Player.BLACK)
    position = _position(board, Player.BLACK)
    legal = get_valid_moves(board)
    provider = _provider(tmp_path)

    calls = []

    def counting_check() -> None:
        calls.append(1)

    provider.policy(
        position, Player.BLACK, legal, timeout_check=counting_check
    )
    assert calls

    def failing_check() -> None:
        raise RuntimeError("deadline")

    with pytest.raises(RuntimeError, match="deadline"):
        provider.policy(
            position, Player.BLACK, legal, timeout_check=failing_check
        )
    with pytest.raises(RuntimeError, match="deadline"):
        provider.value(
            position, Player.BLACK, timeout_check=failing_check
        )


def test_value_in_unit_interval_and_empty_board_half(tmp_path) -> None:
    provider = _provider(tmp_path)
    board = Board(15)
    board.place(7, 7, Player.BLACK)
    position = _position(board, Player.BLACK)

    value = provider.value(position, Player.BLACK)

    assert 0.0 < value < 1.0

    empty = _position(Board(15), Player.BLACK)
    assert provider.value(empty, Player.BLACK) == 0.5


def test_hard_ai_uses_model_provider_and_returns_legal_move(tmp_path) -> None:
    model_path = _tiny_model(tmp_path)
    config = replace(
        DEFAULT_HARD_AI_CONFIG,
        model_path=str(model_path),
        time_limit_ms=200,
        time_safety_margin_ms=10,
    )
    ai = HardAI(Player.WHITE, config=config)
    board = Board(15)
    board.place(7, 7, Player.BLACK)
    board.place(7, 8, Player.WHITE)

    move = ai.choose_move(board)

    assert isinstance(ai.provider, ModelPolicyValueProvider)
    assert move in get_valid_moves(board)
    assert ai.last_search_stats.decision_reason in (
        "mcts_fallback",
        "timeout_fallback",
    )


def test_hard_ai_default_stays_heuristic() -> None:
    ai = HardAI(Player.WHITE)

    assert type(ai.provider).__name__ == "HeuristicPolicyValueProvider"


def test_global_top_k_returns_legal_deterministic_moves(tmp_path) -> None:
    provider = _provider(tmp_path)
    board = Board(15)
    board.place(7, 7, Player.BLACK)
    position = _position(board, Player.BLACK)

    first = provider.global_top_k(position, Player.BLACK, 16)
    second = provider.global_top_k(position, Player.BLACK, 16)

    assert first == second
    assert len(first) == 16
    assert len(set(first)) == 16
    for move in first:
        assert board.is_empty(*move)
    assert (7, 7) not in first


def test_global_top_k_shares_forward_pass_with_policy(tmp_path) -> None:
    provider = _provider(tmp_path)
    provider._ensure_net()

    class CountingNet:
        def __init__(self, net) -> None:
            self._net = net
            self.size = net.size
            self.calls = 0

        def __call__(self, planes):
            self.calls += 1
            return self._net(planes)

    counting = CountingNet(provider._net)
    provider._net = counting
    board = Board(15)
    board.place(7, 7, Player.BLACK)
    position = _position(board, Player.BLACK)
    legal = get_valid_moves(board)

    provider.policy(position, Player.BLACK, legal)
    provider.global_top_k(position, Player.BLACK, 16)

    assert counting.calls == 1


def test_global_top_k_honors_zero_and_full_board(tmp_path) -> None:
    provider = _provider(tmp_path)
    empty_position = _position(Board(15), Player.BLACK)

    assert provider.global_top_k(empty_position, Player.BLACK, 0) == ()
    top = provider.global_top_k(empty_position, Player.BLACK, 16)
    assert len(top) == 16

    full = Board(15)
    for row in range(full.size):
        for col in range(full.size):
            full.place(
                row, col, Player.BLACK if (row + col) % 2 else Player.WHITE
            )
    full_position = _position(full, Player.BLACK)
    assert provider.global_top_k(full_position, Player.BLACK, 16) == ()
