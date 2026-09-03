from pathlib import Path
import sys

import pytest


SRC_DIR = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SRC_DIR))

from gomoku.ai.pattern_matcher import PatternKind, PatternMatcher
from gomoku.ai.threat_search import (
    MODE_AUTO,
    MODE_VCF,
    MODE_VCT,
    SearchStatus,
    ThreatSearch,
    find_forced_defense,
    find_forcing_win,
    find_immediate_win,
)
from gomoku.ai.hard_ai_config import DEFAULT_HARD_AI_CONFIG, HardAIConfig
from gomoku.ai.search_position import SearchPosition
from gomoku.ai.zobrist import ZobristTable
from gomoku.core.board import Board
from gomoku.core.enums import Player


def make_board(stones) -> Board:
    board = Board()
    for row, col, player in stones:
        board.place(row, col, Player(player))
    return board


def make_search(board: Board, config: HardAIConfig | None = None) -> ThreatSearch:
    config = config or DEFAULT_HARD_AI_CONFIG
    zobrist = ZobristTable(board.size, config.zobrist_seed)
    return ThreatSearch(config, zobrist)


# ------------------------------------------------------------ immediate

def test_immediate_win_horizontal_and_returns_deterministic_cell() -> None:
    board = make_board(
        [(7, 4, 2), (7, 5, 2), (7, 6, 2), (7, 7, 2)]
    )
    assert find_immediate_win(board, Player.WHITE) == (7, 8)
    assert find_immediate_win(board, Player.WHITE) == (7, 8)


@pytest.mark.parametrize(
    "stones,expected_pair",
    [
        ([(4, 7, 2), (5, 7, 2), (6, 7, 2), (7, 7, 2)], {(3, 7), (8, 7)}),
        ([(4, 4, 2), (5, 5, 2), (6, 6, 2), (7, 7, 2)], {(3, 3), (8, 8)}),
        ([(4, 10, 2), (5, 9, 2), (6, 8, 2), (7, 7, 2)], {(3, 11), (8, 6)}),
    ],
)
def test_immediate_win_other_directions(stones, expected_pair) -> None:
    board = make_board(stones)
    assert find_immediate_win(board, Player.WHITE) in expected_pair


def test_immediate_win_none_on_scattered_stones() -> None:
    board = make_board([(3, 3, 2), (7, 9, 2), (11, 4, 2)])
    assert find_immediate_win(board, Player.WHITE) is None


def test_immediate_block_opponent_four() -> None:
    board = make_board(
        [(7, 4, 1), (7, 5, 1), (7, 6, 1), (7, 7, 1), (9, 9, 2)]
    )
    assert find_immediate_win(board, Player.BLACK) in {(7, 3), (7, 8)}


# ------------------------------------------------------------------ VCF

def test_vcf_chain_with_three_forced_defenses() -> None:
    board = make_board(
        [
            (7, 4, 2), (7, 5, 2), (7, 6, 2),
            (3, 8, 2), (4, 8, 2), (5, 8, 2),
            (9, 4, 2), (9, 5, 2), (9, 6, 2),
            (7, 2, 1), (7, 8, 1), (2, 8, 1),
        ]
    )
    before = board.to_list()
    result = make_search(board).find_forcing_win(
        board, Player.WHITE, mode=MODE_VCF, time_budget_ms=5000
    )
    assert result.status == SearchStatus.FOUND
    assert result.mode == MODE_VCF
    assert result.first_move == (7, 7)
    assert result.attacker_moves == ((7, 7), (6, 7), (9, 7), (9, 8))
    assert result.forced_defenses == ((7, 3), (8, 5), (9, 3))
    assert result.winning_points == ((9, 8),)
    assert board.to_list() == before


def test_vcf_double_four_two_independent_winning_points() -> None:
    board = make_board(
        [
            (7, 3, 2), (7, 4, 2), (7, 5, 2),
            (4, 6, 2), (5, 6, 2), (6, 6, 2),
        ]
    )
    result = make_search(board).find_forcing_win(
        board, Player.WHITE, mode=MODE_VCF, time_budget_ms=5000
    )
    assert result.status == SearchStatus.FOUND
    assert result.first_move == (7, 6)
    assert len(result.forced_defenses) == 1
    assert len(result.winning_points) >= 2


def test_vcf_verifies_defender_counter_win_refutation() -> None:
    board = make_board(
        [
            (7, 5, 2), (7, 6, 2), (7, 7, 2),
            (7, 9, 1),
            (10, 4, 1), (10, 5, 1), (10, 6, 1), (10, 7, 1),
        ]
    )
    result = make_search(board).find_forcing_win(
        board, Player.WHITE, mode=MODE_VCF, time_budget_ms=5000
    )
    assert result.status == SearchStatus.NOT_FOUND


def test_vcf_simple_chain_found_via_auto_mode() -> None:
    board = make_board(
        [(7, 5, 2), (7, 6, 2), (7, 7, 2), (7, 9, 1), (5, 8, 2), (6, 8, 2)]
    )
    result = make_search(board).find_forcing_win(
        board, Player.WHITE, mode=MODE_AUTO, time_budget_ms=5000
    )
    assert result.status == SearchStatus.FOUND
    assert result.mode == MODE_VCF
    assert result.first_move in {(7, 4), (7, 8)}
    assert result.attacker_moves[0] in {(7, 4), (7, 8)}
    assert len(result.attacker_moves) >= 2
    assert len(result.forced_defenses) >= 1


# ------------------------------------------------------------------ VCT

def test_vct_finds_double_open_three_win_that_vcf_misses() -> None:
    board = make_board(
        [(7, 5, 2), (7, 7, 2), (5, 6, 2), (6, 6, 2)]
    )
    search = make_search(board)
    vcf = search.find_forcing_win(
        board, Player.WHITE, mode=MODE_VCF, time_budget_ms=5000
    )
    assert vcf.status == SearchStatus.NOT_FOUND
    vct = search.find_forcing_win(
        board, Player.WHITE, mode=MODE_VCT, time_budget_ms=5000
    )
    assert vct.status == SearchStatus.FOUND
    assert vct.first_move == (7, 6)
    assert len(vct.attacker_moves) >= 3
    assert len(vct.forced_defenses) >= 2


def test_vct_defender_counter_four_refutes() -> None:
    board = make_board(
        [
            (7, 5, 2), (7, 7, 2), (5, 6, 2), (6, 6, 2),
            (10, 5, 1), (10, 6, 1), (10, 7, 1),
        ]
    )
    result = make_search(board).find_forcing_win(
        board, Player.WHITE, mode=MODE_VCT, time_budget_ms=5000
    )
    assert result.status == SearchStatus.NOT_FOUND


# ----------------------------------------------------- pattern audit

def test_broken_three_patterns_recognized_in_all_directions() -> None:
    matcher = PatternMatcher()
    cases = [
        # XX_X horizontal: gap (7,6) completes the open four.
        ([(7, 4, 2), (7, 5, 2), (7, 7, 2)], (0, 1), (7, 6)),
        # X_XX horizontal.
        ([(7, 4, 2), (7, 6, 2), (7, 7, 2)], (0, 1), (7, 5)),
        ([(4, 7, 2), (5, 7, 2), (7, 7, 2)], (1, 0), (6, 7)),
        ([(4, 7, 2), (6, 7, 2), (7, 7, 2)], (1, 0), (5, 7)),
        ([(4, 4, 2), (5, 5, 2), (7, 7, 2)], (1, 1), (6, 6)),
        ([(4, 4, 2), (6, 6, 2), (7, 7, 2)], (1, 1), (5, 5)),
        ([(4, 10, 2), (5, 9, 2), (7, 7, 2)], (1, -1), (6, 8)),
        ([(4, 10, 2), (6, 8, 2), (7, 7, 2)], (1, -1), (5, 9)),
    ]
    for stones, direction, key in cases:
        board = make_board(stones)
        patterns = matcher.find_patterns(board, Player.WHITE)
        jump = [
            pattern
            for pattern in patterns
            if pattern.kind == PatternKind.JUMP_THREE
            and pattern.direction == direction
        ]
        assert jump, f"no JUMP_THREE for {stones}"
        assert any(key in pattern.key_empties for pattern in jump), (
            f"key {key} missing from {jump}"
        )


def test_gapped_fours_classified_as_closed_with_gap_key() -> None:
    matcher = PatternMatcher()
    cases = [
        ([(7, 4, 2), (7, 5, 2), (7, 6, 2), (7, 8, 2)], (7, 7)),
        ([(7, 4, 2), (7, 5, 2), (7, 7, 2), (7, 8, 2)], (7, 6)),
        ([(4, 7, 2), (5, 7, 2), (6, 7, 2), (8, 7, 2)], (7, 7)),
        ([(4, 4, 2), (5, 5, 2), (6, 6, 2), (8, 8, 2)], (7, 7)),
    ]
    for stones, gap in cases:
        board = make_board(stones)
        patterns = matcher.find_patterns(board, Player.WHITE)
        closed = [
            pattern
            for pattern in patterns
            if pattern.kind == PatternKind.CLOSED_FOUR
        ]
        assert closed, f"no CLOSED_FOUR for {stones}"
        assert any(
            pattern.key_empties == frozenset({gap}) for pattern in closed
        ), f"gap {gap} not the single key in {closed}"


def test_immediate_win_fills_gapped_four() -> None:
    board = make_board(
        [(7, 4, 2), (7, 6, 2), (7, 7, 2), (7, 8, 2)]
    )
    assert find_immediate_win(board, Player.WHITE) == (7, 5)


# ------------------------------------------------ status separation

def test_neutral_position_returns_not_found_quickly() -> None:
    board = make_board(
        [(3, 3, 1), (11, 3, 2), (3, 11, 1), (11, 11, 2)]
    )
    result = make_search(board).find_forcing_win(
        board, Player.WHITE, mode=MODE_AUTO, time_budget_ms=5000
    )
    assert result.status == SearchStatus.NOT_FOUND
    assert result.attacker_moves == ()
    assert result.nodes >= 0


def test_tiny_budget_returns_timeout_with_empty_chain() -> None:
    board = make_board(
        [
            (7, 4, 2), (7, 5, 2), (7, 6, 2),
            (3, 8, 2), (4, 8, 2), (5, 8, 2),
            (7, 2, 1), (7, 8, 1), (2, 8, 1),
        ]
    )
    before = board.to_list()
    result = make_search(board).find_forcing_win(
        board, Player.WHITE, mode=MODE_AUTO, time_budget_ms=1
    )
    assert result.status == SearchStatus.TIMEOUT
    assert result.attacker_moves == ()
    assert result.forced_defenses == ()
    assert board.to_list() == before


# ------------------------------------------------ forced defense

def test_forced_defense_verified_not_blind_chain_head() -> None:
    # Chain ((7,4),(7,3)) claims B(7,4) is the threat, but the real resource
    # is the anti-diagonal group: B(3,7) makes an open four with keys
    # (2,8),(7,3). W(7,4) is verified to lose (BLACK still wins via (3,7)),
    # so the blind chain head must not be returned; W(7,3), the verified
    # defense, kills the only open-four key BLACK has.
    board = make_board(
        [(4, 6, 1), (5, 5, 1), (6, 4, 1)]
    )
    before = board.to_list()
    defense = find_forced_defense(board, Player.WHITE, ((7, 4), (7, 3)))
    assert defense == (7, 3)
    assert board.to_list() == before


def test_forced_defense_returns_none_when_everything_fails() -> None:
    board = make_board(
        [(7, 4, 1), (7, 5, 1), (7, 6, 1), (7, 7, 1), (9, 9, 2)]
    )
    assert find_forced_defense(board, Player.WHITE, ((7, 3),)) is None


def test_forced_defense_status_distinguishes_found() -> None:
    board = make_board(
        [(7, 5, 1), (7, 6, 1), (7, 7, 1), (7, 9, 2)]
    )
    search = make_search(board)
    result = search.find_forced_defense(
        board, Player.WHITE, ((7, 4),), time_budget_ms=5000
    )
    assert result.status == SearchStatus.FOUND
    assert result.forced_defenses == ((7, 4),)


def test_board_immutability_across_all_entry_points() -> None:
    board = make_board(
        [
            (7, 4, 2), (7, 5, 2), (7, 6, 2),
            (3, 8, 2), (4, 8, 2), (5, 8, 2),
            (9, 4, 2), (9, 5, 2), (9, 6, 2),
            (7, 2, 1), (7, 8, 1), (2, 8, 1),
        ]
    )
    before = board.to_list()
    find_immediate_win(board, Player.WHITE)
    find_forcing_win(board, Player.WHITE, time_budget_ms=5000)
    find_forced_defense(board, Player.BLACK, ((7, 7),))
    assert board.to_list() == before


# --------------------------------------- uncapped reply/candidate sets

def _position_for(board: Board, config: HardAIConfig) -> SearchPosition:
    zobrist = ZobristTable(board.size, config.zobrist_seed)
    return SearchPosition.from_board(
        board,
        Player.WHITE,
        zobrist,
        max_candidate_radius=config.candidate_radius,
    )


def test_counter_cells_fully_enumerated_without_cap() -> None:
    # BLACK owns eight horizontal threes (rows 2 apart with alternating
    # column offsets so no vertical fours form across rows); each three
    # contributes two four-creating cells -> 16 counter-four replies. A
    # capped enumeration (the old vct_defender_reply_cap=12) would
    # silently drop four of them.
    stones = [
        (row, col, 1)
        for row in range(0, 15, 2)
        for col in ((2, 3, 4) if row % 4 == 0 else (8, 9, 10))
    ]
    board = make_board(stones)
    search = make_search(board)
    position = _position_for(board, DEFAULT_HARD_AI_CONFIG)
    replies = search._counter_cells(
        position, Player.BLACK, blocks=set(), timeout_check=None
    )
    expected = {
        (row, col)
        for row in range(0, 15, 2)
        for col in (
            (1, 5) if row % 4 == 0 else (7, 11)
        )
    }
    assert set(replies) == expected
    assert len(replies) == 16


def test_defense_candidates_fully_enumerated_without_cap() -> None:
    chain = ((7, 7), (8, 8), (9, 9), (6, 8), (8, 6))
    board = Board()
    search = make_search(board)
    position = _position_for(board, DEFAULT_HARD_AI_CONFIG)
    candidates = search._defense_candidates(position, chain, None)
    expected = set(chain)
    for row, col in chain:
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                cell = (row + dr, col + dc)
                if (
                    board.is_inside(cell[0], cell[1])
                    and position.is_empty(*cell)
                ):
                    expected.add(cell)
    assert set(candidates) == expected
    assert candidates[: len(chain)] == chain
    assert len(candidates) > 24  # the old defense_candidate_cap


def test_forced_defense_deadline_during_enumeration_returns_timeout() -> None:
    board = make_board([(7, 5, 1), (7, 6, 1), (7, 7, 1)])
    zobrist = ZobristTable(board.size, DEFAULT_HARD_AI_CONFIG.zobrist_seed)
    calls = iter([0.0])

    def clock() -> float:
        try:
            return next(calls)
        except StopIteration:
            return 1e12

    search = ThreatSearch(DEFAULT_HARD_AI_CONFIG, zobrist, clock=clock)
    result = search.find_forced_defense(
        board, Player.WHITE, ((7, 4), (7, 3)), time_budget_ms=5000
    )
    assert result.status == SearchStatus.TIMEOUT
    assert result.forced_defenses == ()
