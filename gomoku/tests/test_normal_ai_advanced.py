from dataclasses import replace
from pathlib import Path
import sys
from types import SimpleNamespace


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from gomoku.ai.normal_ai import NormalAI
from gomoku.ai.normal_ai_config import DEFAULT_NORMAL_AI_CONFIG
from gomoku.ai.pattern_matcher import PatternKind
from gomoku.ai.search_position import SearchPosition
from gomoku.ai.zobrist import ZobristTable
from gomoku.core.board import Board
from gomoku.core.enums import Player


def make_position(board: Board, player=Player.WHITE) -> SearchPosition:
    return SearchPosition.from_board(
        board,
        player,
        ZobristTable(board.size, 404),
    )


def test_optional_quiescence_moves_keep_stand_pat_available() -> None:
    board = Board()
    for col in range(5, 8):
        board.place(7, col, Player.WHITE)
    ai = NormalAI(Player.WHITE)
    position = make_position(board)
    ai._deadline = float("inf")
    stand_pat = ai._evaluate(position)

    score = ai._quiescence(
        position,
        -ai.config.infinity_score,
        ai.config.infinity_score,
        ply=0,
        color=1,
        extension_depth=2,
        tt_move=None,
    )
    assert score >= stand_pat
    assert position.grid == board.grid


def test_fixed_node_budget_is_reproducible() -> None:
    board = Board()
    board.place(7, 7, Player.BLACK)
    config = replace(
        DEFAULT_NORMAL_AI_CONFIG,
        time_limit_ms=10_000,
        max_nodes=120,
        max_depth=6,
        enable_vcf=False,
    )
    first = NormalAI(Player.WHITE, config=config)
    second = NormalAI(Player.WHITE, config=config)
    assert first.choose_move(board) == second.choose_move(board)
    assert first.last_search_stats.nodes <= 121
    assert first.last_search_stats.timed_out is True


def test_pvs_and_aspiration_match_full_window_search() -> None:
    board = Board()
    for row, col, player in (
        (7, 7, Player.BLACK),
        (7, 8, Player.WHITE),
        (8, 8, Player.BLACK),
    ):
        board.place(row, col, player)
    common = dict(
        time_limit_ms=10_000,
        max_depth=2,
        threat_extension_depth=0,
        enable_vcf=False,
        root_max_quiet_candidates=5,
        inner_max_quiet_candidates=5,
    )
    optimized = NormalAI(
        Player.WHITE,
        config=replace(DEFAULT_NORMAL_AI_CONFIG, **common),
    )
    baseline = NormalAI(
        Player.WHITE,
        config=replace(
            DEFAULT_NORMAL_AI_CONFIG,
            **common,
            enable_pvs=False,
            aspiration_window=0,
        ),
    )
    assert optimized.choose_move(board) == baseline.choose_move(board)


def test_evaluation_cache_and_search_report_are_populated() -> None:
    board = Board()
    board.place(7, 7, Player.BLACK)
    config = replace(
        DEFAULT_NORMAL_AI_CONFIG,
        time_limit_ms=10_000,
        max_depth=1,
        threat_extension_depth=0,
        enable_vcf=False,
    )
    ai = NormalAI(Player.WHITE, config=config)
    ai.choose_move(board)
    stats = ai.last_search_stats
    assert stats.depth_results[-1].depth == 1
    assert stats.root_moves
    assert stats.max_ply >= 1


def test_vcf_finds_open_four_creation_without_mutating_board() -> None:
    board = Board()
    for col in range(5, 8):
        board.place(7, col, Player.WHITE)
    board.place(6, 6, Player.BLACK)
    before = board.to_list()
    config = replace(
        DEFAULT_NORMAL_AI_CONFIG,
        time_limit_ms=10_000,
        vcf_time_fraction=0.5,
    )
    ai = NormalAI(Player.WHITE, config=config)
    move = ai.choose_move(board)
    assert move in {(7, 4), (7, 8)}
    assert ai.last_search_stats.vcf_found is True
    assert ai.last_search_stats.vcf_nodes > 0
    assert board.to_list() == before


def test_defensive_vcf_restricts_root_to_moves_that_break_forced_attack() -> None:
    board = Board()
    for col in (5, 6, 7):
        board.place(7, col, Player.BLACK)
    before = board.to_list()
    config = replace(
        DEFAULT_NORMAL_AI_CONFIG,
        time_limit_ms=10_000,
        max_depth=2,
        vcf_time_fraction=0.5,
        defensive_vcf_time_fraction=0.5,
    )
    ai = NormalAI(Player.WHITE, config=config)

    move = ai.choose_move(board)

    assert ai.last_search_stats.defensive_vcf_detected is True
    assert set(ai.last_search_stats.defensive_vcf_moves) == {(7, 4), (7, 8)}
    assert {(7, 4), (7, 8)}.issubset(
        set(ai.last_search_stats.defensive_vcf_proof_candidates)
    )
    assert ai.last_search_stats.defensive_vcf_budget_ms > 0
    assert ai.last_search_stats.vcf_elapsed_ms >= 0
    assert move in ai.last_search_stats.defensive_vcf_moves
    assert board.to_list() == before


def test_vcf_proof_candidates_ignore_ordinary_defense_limit() -> None:
    board = Board()
    for col in (5, 6, 7):
        board.place(7, col, Player.BLACK)
    config = replace(
        DEFAULT_NORMAL_AI_CONFIG,
        time_limit_ms=10_000,
        max_depth=1,
        vcf_defense_max_candidates=0,
        defensive_vcf_time_fraction=0.5,
    )
    ai = NormalAI(Player.WHITE, config=config)

    move = ai.choose_move(board)

    assert ai.last_search_stats.defensive_vcf_detected is True
    assert move in {(7, 4), (7, 8)}


def test_dynamic_vcf_budget_tracks_pattern_urgency() -> None:
    ai = NormalAI(Player.WHITE)
    closed_three = [SimpleNamespace(kind=PatternKind.CLOSED_THREE)]
    jump_threes = [
        SimpleNamespace(kind=PatternKind.JUMP_THREE),
        SimpleNamespace(kind=PatternKind.JUMP_THREE),
    ]

    low = ai._vcf_budget_ms(1_000, closed_three, 0.2)
    high = ai._vcf_budget_ms(1_000, jump_threes, 0.2)

    assert 0 < low < high <= 200


def test_dynamic_vcf_budget_can_be_disabled_for_fixed_fraction() -> None:
    ai = NormalAI(
        Player.WHITE,
        config=replace(
            DEFAULT_NORMAL_AI_CONFIG,
            enable_dynamic_vcf_budget=False,
        ),
    )
    patterns = [SimpleNamespace(kind=PatternKind.CLOSED_THREE)]
    assert ai._vcf_budget_ms(1_000, patterns, 0.2) == 200
