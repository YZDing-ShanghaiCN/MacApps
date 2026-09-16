from dataclasses import replace
from pathlib import Path
import random
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
    assert first.reuse_plies == 0

    # Same position again: the clean completion allows root reuse. Simulating
    # through the reused subtree exercises the re-linked parent chain in the
    # backup loop (stale parents would crash with an AttributeError).
    second = mcts.search(board, Player.WHITE, time_budget_ms=200)
    assert second.timed_out is False
    assert second.simulations == 40
    assert second.root_visits == second.simulations
    assert second.move is not None
    assert board.is_empty(*second.move)
    assert second.reuse_plies == 1


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


def _noisy_mcts(config) -> MCTS:
    return MCTS(
        config,
        HeuristicPolicyValueProvider(config),
        clock=lambda: 0.0,
    )


def test_root_noise_is_normalized_and_flagged() -> None:
    config = replace(DEFAULT_HARD_AI_CONFIG, mcts_node_capacity=60)
    mcts = _noisy_mcts(config)
    board = make_board([(7, 7, 1), (8, 8, 2), (6, 6, 1)])
    result = mcts.search(
        board,
        Player.WHITE,
        time_budget_ms=200,
        root_noise=True,
        noise_rng=random.Random(1),
    )

    assert result.root_noise_applied is True
    priors = mcts._reuse_subtree.priors
    assert priors
    assert abs(sum(priors.values()) - 1.0) < 1e-9
    assert all(value >= 0.0 for value in priors.values())


def test_root_noise_deterministic_for_same_seed() -> None:
    config = replace(DEFAULT_HARD_AI_CONFIG, mcts_node_capacity=60)
    board = make_board([(7, 7, 1), (8, 8, 2), (6, 6, 1)])

    def run(seed: int):
        return _noisy_mcts(config).search(
            board,
            Player.WHITE,
            time_budget_ms=200,
            root_noise=True,
            noise_rng=random.Random(seed),
        )

    first = run(7)
    second = run(7)
    assert first.move == second.move
    assert first.root_moves == second.root_moves


def test_root_noise_different_seed_changes_priors() -> None:
    config = replace(DEFAULT_HARD_AI_CONFIG, mcts_node_capacity=60)
    board = make_board([(7, 7, 1), (8, 8, 2), (6, 6, 1)])

    def run(seed: int):
        mcts = _noisy_mcts(config)
        mcts.search(
            board,
            Player.WHITE,
            time_budget_ms=200,
            root_noise=True,
            noise_rng=random.Random(seed),
        )
        return mcts._reuse_subtree.priors

    assert run(1) != run(2)


def test_default_search_is_noise_free() -> None:
    config = replace(DEFAULT_HARD_AI_CONFIG, mcts_node_capacity=60)
    board = make_board([(7, 7, 1), (8, 8, 2), (6, 6, 1)])
    mcts = _noisy_mcts(config)
    result = mcts.search(board, Player.WHITE, time_budget_ms=200)

    assert result.root_noise_applied is False

    explicit_off = _noisy_mcts(config).search(
        board,
        Player.WHITE,
        time_budget_ms=200,
        root_noise=False,
        noise_rng=random.Random(99),
    )
    assert explicit_off.root_noise_applied is False
    assert explicit_off.root_moves == result.root_moves
    assert explicit_off.move == result.move


def test_dirichlet_noise_helper_normalizes_and_replays() -> None:
    from gomoku.ai.mcts import apply_dirichlet_noise

    priors = {
        (7, 7): 0.5,
        (7, 8): 0.3,
        (6, 6): 0.2,
    }
    first = apply_dirichlet_noise(priors, random.Random(5), 0.25, 0.03)
    second = apply_dirichlet_noise(priors, random.Random(5), 0.25, 0.03)
    other = apply_dirichlet_noise(priors, random.Random(6), 0.25, 0.03)
    untouched = apply_dirichlet_noise(priors, random.Random(5), 0.0, 0.03)

    assert first == second
    assert first != other
    assert untouched == priors
    assert abs(sum(first.values()) - 1.0) < 1e-12
    assert all(value >= 0.0 for value in first.values())
    assert set(first) == set(priors)


class _FakeGlobalProvider:
    """Uniform-prior provider with a configurable whole-board Top-K hook."""

    def __init__(self, top_k: tuple[tuple[int, int], ...] = ()) -> None:
        self.top_k = top_k
        self.top_k_calls = 0

    def global_top_k(self, position, player, k, *, timeout_check=None):
        self.top_k_calls += 1
        return self.top_k

    def policy(self, position, player, legal_moves, *, timeout_check=None):
        if timeout_check is not None:
            timeout_check()
        share = 1.0 / len(legal_moves)
        return {move: share for move in legal_moves}

    def value(self, position, player, *, timeout_check=None):
        if timeout_check is not None:
            timeout_check()
        return 0.5


def _pw_mcts(provider=None, **overrides) -> MCTS:
    config = replace(
        DEFAULT_HARD_AI_CONFIG,
        mcts_pw_initial_children=4,
        mcts_pw_growth=8.0,
        **overrides,
    )
    return MCTS(
        config,
        provider or HeuristicPolicyValueProvider(config),
        clock=lambda: 0.0,
    )


def test_progressive_widening_exposes_more_root_children() -> None:
    board = make_board([(7, 7, 1), (8, 8, 2)])
    low = _pw_mcts(mcts_node_capacity=8).search(
        board, Player.WHITE, time_budget_ms=100
    )
    high = _pw_mcts(mcts_node_capacity=64).search(
        board, Player.WHITE, time_budget_ms=100
    )

    assert low.simulations == 8
    assert high.simulations == 64
    assert len(low.root_moves) == 8
    assert len(low.root_moves) < len(high.root_moves)


def test_widening_visits_formula_and_disabled_mode() -> None:
    mcts = _pw_mcts()
    assert mcts._children_allowed(0) == 4
    assert mcts._children_allowed(4) == 4 + int(8.0 * 2.0)
    assert mcts._children_allowed(9) == 4 + 24

    disabled = _pw_mcts(mcts_pw_enabled=False)
    assert disabled._children_allowed(0) > 10 ** 8


def test_disabled_widening_keeps_full_pool_untried() -> None:
    board = make_board([(7, 7, 1), (8, 8, 2)])
    disabled = _pw_mcts(mcts_pw_enabled=False, mcts_node_capacity=8)
    disabled.search(board, Player.WHITE, time_budget_ms=100)
    root = disabled._reuse_subtree
    assert root.pending == []
    assert len(root.untried) == len(root.priors) - 8

    enabled = _pw_mcts(mcts_node_capacity=8)
    enabled.search(board, Player.WHITE, time_budget_ms=100)
    enabled_root = enabled._reuse_subtree
    assert enabled_root.pending != []


def test_global_top_k_nonlocal_move_enters_tree() -> None:
    board = make_board([(7, 7, 1)])
    provider = _FakeGlobalProvider(top_k=((0, 0),))
    mcts = _pw_mcts(provider=provider, mcts_node_capacity=30)
    result = mcts.search(board, Player.WHITE, time_budget_ms=100)

    visited = {item.move for item in result.root_moves}
    assert (0, 0) in visited
    assert provider.top_k_calls > 0
    assert result.move is not None
    assert board.is_empty(*result.move)


def test_global_top_k_illegal_cells_are_filtered() -> None:
    board = make_board([(7, 7, 1)])
    provider = _FakeGlobalProvider(top_k=((7, 7), (-1, 0), (15, 0)))
    mcts = _pw_mcts(provider=provider, mcts_node_capacity=30)
    result = mcts.search(board, Player.WHITE, time_budget_ms=100)

    visited = {item.move for item in result.root_moves}
    assert (7, 7) not in visited
    assert all(0 <= row < 15 and 0 <= col < 15 for row, col in visited)
    assert result.move is not None
    assert board.is_empty(*result.move)


def test_global_top_k_zero_skips_provider_hook() -> None:
    board = make_board([(7, 7, 1)])
    provider = _FakeGlobalProvider(top_k=((0, 0),))
    mcts = _pw_mcts(
        provider=provider,
        mcts_node_capacity=30,
        mcts_global_top_k=0,
    )
    result = mcts.search(board, Player.WHITE, time_budget_ms=100)

    assert provider.top_k_calls == 0
    assert (0, 0) not in {item.move for item in result.root_moves}


def _reroot_mcts() -> MCTS:
    config = replace(DEFAULT_HARD_AI_CONFIG, mcts_node_capacity=40)
    return MCTS(
        config,
        HeuristicPolicyValueProvider(config),
        clock=lambda: 0.0,
    )


def test_two_ply_reroot_reuses_visits_across_opponent_move() -> None:
    # Per-color usage (like a HardAI that only plays its own turns): the
    # instance searches P, plays m1, and searches P+m1+m2 after the
    # opponent replies with the top move of the stored subtree.
    mcts = _reroot_mcts()
    board = make_board([(7, 7, 1), (8, 8, 2)])
    first = mcts.search(board, Player.WHITE, time_budget_ms=100)
    assert first.reuse_plies == 0
    assert first.move is not None
    our_move = first.move

    played = make_board([(7, 7, 1), (8, 8, 2), (*our_move, 2)])
    subtree = mcts._reuse_subtree.children[our_move]
    opp_move = max(
        subtree.children,
        key=lambda move: subtree.children[move].visits,
    )
    continuation = make_board(
        [(7, 7, 1), (8, 8, 2), (*our_move, 2), (*opp_move, 1)]
    )

    rerooted = mcts.search(continuation, Player.WHITE, time_budget_ms=100)

    assert rerooted.reuse_plies == 2
    assert rerooted.simulations == 40
    assert rerooted.move is not None
    assert continuation.is_empty(*rerooted.move)
    for move in mcts._reuse_subtree.children:
        assert continuation.is_empty(*move)

    fresh_mcts = _reroot_mcts()
    fresh = fresh_mcts.search(
        continuation, Player.WHITE, time_budget_ms=100
    )
    assert fresh.reuse_plies == 0
    assert mcts._reuse_subtree.visits > fresh_mcts._reuse_subtree.visits


def test_one_ply_reroot_across_turns() -> None:
    # Shared-instance usage (one MCTS for both colors): the opponent's next
    # search advances the stored subtree through our just-played move.
    mcts = _reroot_mcts()
    board = make_board([(7, 7, 1), (8, 8, 2)])
    first = mcts.search(board, Player.WHITE, time_budget_ms=100)
    our_move = first.move
    played = make_board([(7, 7, 1), (8, 8, 2), (*our_move, 2)])

    second = mcts.search(played, Player.BLACK, time_budget_ms=100)

    assert second.reuse_plies == 2
    assert second.move is not None
    assert played.is_empty(*second.move)
    for move in mcts._reuse_subtree.children:
        assert played.is_empty(*move)


def test_reroot_discards_on_opponent_mismatch() -> None:
    from gomoku.core.rules import get_valid_moves

    mcts = _reroot_mcts()
    board = make_board([(7, 7, 1), (8, 8, 2)])
    first = mcts.search(board, Player.WHITE, time_budget_ms=100)
    our_move = first.move
    played = make_board([(7, 7, 1), (8, 8, 2), (*our_move, 2)])

    subtree = mcts._reuse_subtree.children[our_move]
    explored = set(subtree.children)
    alternatives = [
        move for move in get_valid_moves(played) if move not in explored
    ]
    assert alternatives  # some reply was not explored in the stored subtree
    opp_move = alternatives[0]
    continuation = make_board(
        [(7, 7, 1), (8, 8, 2), (*our_move, 2), (*opp_move, 1)]
    )

    rerooted = mcts.search(continuation, Player.WHITE, time_budget_ms=100)
    assert rerooted.reuse_plies == 0

    fresh = _reroot_mcts().search(
        continuation, Player.WHITE, time_budget_ms=100
    )
    assert rerooted.root_moves == fresh.root_moves
    assert rerooted.move == fresh.move
