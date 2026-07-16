from dataclasses import replace
from pathlib import Path
import sys


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from gomoku.ai.normal_ai import NormalAI, SearchTimeout
from gomoku.ai.normal_ai_config import DEFAULT_NORMAL_AI_CONFIG
from gomoku.ai.search_position import SearchPosition
from gomoku.ai.zobrist import ZobristTable
from gomoku.core.board import Board
from gomoku.core.enums import Player


def test_normal_ai_takes_immediate_win() -> None:
    board = Board()
    for col in range(4, 8):
        board.place(7, col, Player.WHITE)
    assert NormalAI(Player.WHITE).choose_move(board) in {(7, 3), (7, 8)}


def test_normal_ai_blocks_immediate_loss() -> None:
    board = Board()
    for col in range(4, 8):
        board.place(7, col, Player.BLACK)
    assert NormalAI(Player.WHITE).choose_move(board) in {(7, 3), (7, 8)}


def test_extreme_time_limit_still_returns_legal_move_and_preserves_board() -> None:
    board = Board()
    board.place(7, 7, Player.BLACK)
    before = board.to_list()
    config = replace(DEFAULT_NORMAL_AI_CONFIG, time_limit_ms=0)
    move = NormalAI(Player.WHITE, config=config).choose_move(board)

    assert move is not None
    assert board.is_empty(*move)
    assert board.to_list() == before


def test_same_position_is_reproducible_with_fixed_depth_budget() -> None:
    board = Board()
    board.place(7, 7, Player.BLACK)
    config = replace(
        DEFAULT_NORMAL_AI_CONFIG,
        time_limit_ms=10_000,
        max_depth=1,
        threat_extension_depth=0,
    )
    first = NormalAI(Player.WHITE, config=config).choose_move(board)
    second = NormalAI(Player.WHITE, config=config).choose_move(board)
    assert first == second


def test_completed_search_does_not_change_real_board() -> None:
    board = Board()
    board.place(7, 7, Player.BLACK)
    before = board.to_list()
    config = replace(
        DEFAULT_NORMAL_AI_CONFIG,
        time_limit_ms=10_000,
        max_depth=1,
        threat_extension_depth=0,
    )

    move = NormalAI(Player.WHITE, config=config).choose_move(board)
    assert move is not None and board.is_empty(*move)
    assert board.to_list() == before


def test_timeout_discards_incomplete_depth_and_returns_last_complete_move() -> None:
    class ControlledAI(NormalAI):
        def _search_root(self, position, depth):
            if depth == 1:
                return 10, (6, 6)
            raise SearchTimeout

    board = Board()
    board.place(7, 7, Player.BLACK)
    config = replace(DEFAULT_NORMAL_AI_CONFIG, time_limit_ms=10_000)
    ai = ControlledAI(Player.WHITE, config=config)

    assert ai.choose_move(board) == (6, 6)
    assert ai.last_search_stats.completed_depth == 1
    assert ai.last_search_stats.timed_out is True


def test_alpha_beta_matches_unpruned_search_at_small_depth() -> None:
    board = Board()
    board.place(7, 7, Player.BLACK)
    board.place(7, 8, Player.WHITE)
    board.place(8, 8, Player.BLACK)
    common = dict(
        time_limit_ms=10_000,
        max_depth=2,
        threat_extension_depth=0,
        root_max_quiet_candidates=4,
        inner_max_quiet_candidates=4,
    )
    pruned = NormalAI(
        Player.WHITE,
        config=replace(DEFAULT_NORMAL_AI_CONFIG, **common),
    )
    unpruned = NormalAI(
        Player.WHITE,
        config=replace(
            DEFAULT_NORMAL_AI_CONFIG,
            **common,
            enable_alpha_beta=False,
        ),
    )

    assert pruned.choose_move(board) == unpruned.choose_move(board)
    assert pruned.last_search_stats.nodes <= unpruned.last_search_stats.nodes


def test_terminal_score_prefers_fast_win_and_delays_loss() -> None:
    board = Board()
    for col in range(4, 8):
        board.place(7, col, Player.WHITE)
    ai = NormalAI(Player.WHITE)
    position = SearchPosition.from_board(
        board,
        Player.WHITE,
        ZobristTable(board.size, 7),
    )
    position.make_move(7, 8)
    ai._deadline = float("inf")

    quick_loss_for_side_to_move = ai._negamax(
        position,
        1,
        -ai.config.infinity_score,
        ai.config.infinity_score,
        ply=1,
        color=-1,
        extension_depth=0,
    )
    later_loss_for_side_to_move = ai._negamax(
        position,
        1,
        -ai.config.infinity_score,
        ai.config.infinity_score,
        ply=3,
        color=-1,
        extension_depth=0,
    )
    assert quick_loss_for_side_to_move == -ai.config.mate_score + 1
    assert later_loss_for_side_to_move == -ai.config.mate_score + 3
    assert -quick_loss_for_side_to_move > -later_loss_for_side_to_move
