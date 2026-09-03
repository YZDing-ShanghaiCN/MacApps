import json
import threading
import time
from dataclasses import asdict, replace
from pathlib import Path
import sys


SRC_DIR = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SRC_DIR))

from gomoku.ai.hard_ai import (
    HardAI,
    REASON_IMMEDIATE_BLOCK,
    REASON_IMMEDIATE_WIN,
    REASON_MCTS,
    REASON_TACTICAL_DEFENSE,
    REASON_TIMEOUT,
    REASON_VCF,
    REASON_VCT,
)
from gomoku.ai.hard_ai_config import DEFAULT_HARD_AI_CONFIG, HardAIConfig
from gomoku.ai.threat_search import MODE_AUTO, SearchStatus, ThreatSearch
from gomoku.ai.zobrist import ZobristTable
from gomoku.core.board import Board
from gomoku.core.enums import Player
from gomoku.core.rules import get_valid_moves


FAST_CONFIG = replace(
    DEFAULT_HARD_AI_CONFIG, time_limit_ms=150, time_safety_margin_ms=10
)


def make_board(stones) -> Board:
    board = Board()
    for row, col, player in stones:
        board.place(row, col, Player(player))
    return board


def make_ai(
    player: Player = Player.WHITE,
    config: HardAIConfig | None = None,
    clock=None,
) -> HardAI:
    return HardAI(
        player,
        config=config or DEFAULT_HARD_AI_CONFIG,
        clock=clock or time.monotonic,
    )


def test_own_immediate_win_beats_opponent_block() -> None:
    board = make_board(
        [
            (7, 4, 1), (7, 5, 1), (7, 6, 1), (7, 7, 1),
            (4, 0, 2), (5, 0, 2), (6, 0, 2), (7, 0, 2),
        ]
    )
    before = board.to_list()
    ai = make_ai(player=Player.BLACK)
    move = ai.choose_move(board)
    assert move in {(7, 3), (7, 8)}
    stats = ai.last_search_stats
    assert stats.decision_reason == REASON_IMMEDIATE_WIN
    assert stats.immediate_status == "found"
    assert board.to_list() == before


def test_immediate_opponent_block() -> None:
    board = make_board(
        [
            (7, 5, 2), (7, 6, 2), (7, 7, 2), (7, 8, 2),
            (3, 3, 1), (4, 4, 1),
        ]
    )
    before = board.to_list()
    ai = make_ai(player=Player.BLACK)
    move = ai.choose_move(board)
    assert move in {(7, 4), (7, 9)}
    assert ai.last_search_stats.decision_reason == REASON_IMMEDIATE_BLOCK
    assert board.to_list() == before


def test_vcf_forced_win_reason_and_status() -> None:
    board = make_board(
        [
            (7, 4, 2), (7, 5, 2), (7, 6, 2),
            (3, 8, 2), (4, 8, 2), (5, 8, 2),
            (9, 4, 2), (9, 5, 2), (9, 6, 2),
            (7, 2, 1), (7, 8, 1), (2, 8, 1),
        ]
    )
    before = board.to_list()
    ai = make_ai(player=Player.WHITE)
    move = ai.choose_move(board)
    assert move == (7, 7)
    stats = ai.last_search_stats
    assert stats.decision_reason == REASON_VCF
    assert stats.vcf_status == "found"
    assert stats.vcf_proof[0] == (7, 7)
    assert len(stats.vcf_proof) >= 2
    assert board.to_list() == before


def test_vct_forced_win_reason_and_status() -> None:
    board = make_board([(7, 5, 2), (7, 7, 2), (5, 6, 2), (6, 6, 2)])
    before = board.to_list()
    ai = make_ai(player=Player.WHITE)
    move = ai.choose_move(board)
    assert move == (7, 6)
    stats = ai.last_search_stats
    assert stats.decision_reason == REASON_VCT
    assert stats.vcf_status == "not_found"
    assert stats.vct_status == "found"
    assert stats.vct_proof[0] == (7, 6)
    assert len(stats.vct_proof) >= 3
    assert board.to_list() == before


def test_quiet_board_runs_tactical_stages_then_mcts() -> None:
    board = make_board([(0, 0, 1), (14, 14, 2), (0, 14, 1), (14, 0, 2)])
    before = board.to_list()
    ai = make_ai(config=FAST_CONFIG)
    move = ai.choose_move(board)
    stats = ai.last_search_stats
    assert stats.decision_reason == REASON_MCTS
    assert stats.vcf_status == "not_found"
    assert stats.vct_status == "not_found"
    assert stats.defense_status == ""
    assert move in get_valid_moves(board)
    assert board.to_list() == before


def test_tactical_defense_verified_move() -> None:
    board = make_board([(4, 6, 1), (5, 5, 1), (6, 4, 1)])
    before = board.to_list()
    ai = make_ai(player=Player.WHITE)
    move = ai.choose_move(board)
    stats = ai.last_search_stats
    assert stats.decision_reason == REASON_TACTICAL_DEFENSE
    assert stats.defense_status == "found"
    assert move == stats.defense_move
    assert move in {(3, 7), (7, 3)}
    assert board.to_list() == before

    # The chosen defense must actually stop BLACK's forcing win.
    board.place(*move, Player.WHITE)
    verifier = ThreatSearch(
        DEFAULT_HARD_AI_CONFIG,
        ZobristTable(board.size, DEFAULT_HARD_AI_CONFIG.zobrist_seed),
    )
    after = verifier.find_forcing_win(
        board, Player.BLACK, mode=MODE_AUTO, time_budget_ms=2000
    )
    assert after.status == SearchStatus.NOT_FOUND


def test_neutral_position_falls_back_to_mcts() -> None:
    board = make_board([(0, 0, 1), (14, 14, 2), (0, 14, 1), (14, 0, 2)])
    before = board.to_list()
    ai = make_ai(config=FAST_CONFIG)
    move = ai.choose_move(board)
    stats = ai.last_search_stats
    assert stats.decision_reason == REASON_MCTS
    assert stats.mcts_simulations > 0
    assert stats.mcts_root_visits == stats.mcts_simulations
    assert move in get_valid_moves(board)
    assert board.to_list() == before


def test_empty_board_returns_center() -> None:
    board = Board()
    before = board.to_list()
    ai = make_ai()
    move = ai.choose_move(board)
    assert move == (7, 7)
    stats = ai.last_search_stats
    assert stats.decision_reason == REASON_MCTS
    assert stats.mcts_simulations == 0
    assert board.to_list() == before


def test_near_full_board_returns_only_empty_cell() -> None:
    board = Board()
    for row in range(board.size):
        for col in range(board.size):
            if (row, col) == (7, 7):
                continue
            board.place(row, col, Player(1 + ((row * board.size + col) % 2)))
    before = board.to_list()
    ai = make_ai()
    move = ai.choose_move(board)
    assert move == (7, 7)
    assert board.to_list() == before


def test_full_board_returns_none() -> None:
    board = Board()
    for row in range(board.size):
        for col in range(board.size):
            board.place(row, col, Player(1 + ((row * board.size + col) % 2)))
    ai = make_ai()
    move = ai.choose_move(board)
    assert move is None
    assert ai.last_search_stats.decision_reason == "not_searched"


def test_deadline_clock_yields_legal_timeout_fallback() -> None:
    board = make_board([(0, 0, 1), (14, 14, 2)])
    before = board.to_list()
    calls = iter([0.0])

    def clock() -> float:
        try:
            return next(calls)
        except StopIteration:
            return 1e12

    ai = make_ai(clock=clock)
    move = ai.choose_move(board)
    assert move in get_valid_moves(board)
    stats = ai.last_search_stats
    assert stats.decision_reason == REASON_TIMEOUT
    assert stats.timed_out
    assert stats.selected_move == move
    assert board.to_list() == before


def test_tiny_time_budget_returns_legal_fallback_without_raise() -> None:
    config = replace(
        DEFAULT_HARD_AI_CONFIG, time_limit_ms=1, time_safety_margin_ms=0
    )
    board = make_board([(0, 0, 1), (14, 14, 2)])
    before = board.to_list()
    ai = make_ai(config=config)
    move = ai.choose_move(board)
    assert move in get_valid_moves(board)
    stats = ai.last_search_stats
    assert stats.decision_reason in (REASON_TIMEOUT, REASON_MCTS)
    if stats.decision_reason == REASON_TIMEOUT:
        assert stats.timed_out
    assert board.to_list() == before


def test_pre_set_cancel_yields_legal_move_without_raise() -> None:
    board = make_board([(0, 0, 1), (14, 14, 2)])
    before = board.to_list()
    ai = make_ai(config=FAST_CONFIG)
    cancel = threading.Event()
    cancel.set()
    move = ai.choose_move(board, cancel_event=cancel)
    assert move in get_valid_moves(board)
    stats = ai.last_search_stats
    assert stats.decision_reason == REASON_TIMEOUT
    assert stats.timed_out
    assert board.to_list() == before


def test_stats_asdict_is_json_serializable() -> None:
    ai = make_ai(config=FAST_CONFIG)
    ai.choose_move(make_board([(0, 0, 1), (14, 14, 2)]))
    stats = ai.last_search_stats
    payload = asdict(stats)
    encoded = json.dumps(payload)
    decoded = json.loads(encoded)
    assert decoded["decision_reason"] == stats.decision_reason
    assert decoded["selected_move"] == list(stats.selected_move)
