from pathlib import Path
import sys
from collections import Counter
from itertools import product

import pytest


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from gomoku.ai.pattern_matcher import PatternKind, PatternMatcher
from gomoku.core.board import Board
from gomoku.core.enums import Player


def kinds(board: Board, player=Player.BLACK):
    return {pattern.kind for pattern in PatternMatcher().find_patterns(board, player)}


@pytest.mark.parametrize(
    ("stones", "expected"),
    [
        ([(7, col) for col in range(5, 9)], PatternKind.OPEN_FOUR),
        ([(0, col) for col in range(4)], PatternKind.CLOSED_FOUR),
        ([(7, col) for col in range(6, 9)], PatternKind.OPEN_THREE),
        ([(7, col) for col in (5, 7, 8)], PatternKind.JUMP_THREE),
        ([(7, col) for col in (5, 6, 8)], PatternKind.JUMP_THREE),
        ([(0, col) for col in range(3)], PatternKind.CLOSED_THREE),
    ],
)
def test_recognizes_required_pattern_families(stones, expected) -> None:
    board = Board()
    for move in stones:
        board.place(*move, Player.BLACK)
    assert expected in kinds(board)


@pytest.mark.parametrize("columns", [(4, 5, 7, 8), (4, 6, 7, 8)])
def test_recognizes_gapped_four(columns) -> None:
    board = Board()
    for col in columns:
        board.place(7, col, Player.BLACK)

    patterns = PatternMatcher().find_patterns(board, Player.BLACK)
    matching = [p for p in patterns if p.kind == PatternKind.CLOSED_FOUR]
    assert matching
    assert any((7, 6) in p.key_empties or (7, 5) in p.key_empties for p in matching)


def test_overlapping_windows_do_not_duplicate_an_open_four() -> None:
    board = Board()
    for col in range(5, 9):
        board.place(7, col, Player.BLACK)

    patterns = PatternMatcher().find_patterns(board, Player.BLACK)
    open_fours = [p for p in patterns if p.kind == PatternKind.OPEN_FOUR]
    assert len(open_fours) == 1
    assert open_fours[0].key_empties == {(7, 4), (7, 9)}


def test_corner_pattern_treats_board_edge_as_blocked() -> None:
    board = Board()
    for index in range(4):
        board.place(index, index, Player.BLACK)
    assert PatternKind.CLOSED_FOUR in kinds(board)


@pytest.mark.parametrize(
    "stones",
    [
        [(row, 7) for row in range(5, 8)],
        [(index, index) for index in range(5, 8)],
        [(index, 14 - index) for index in range(5, 8)],
    ],
)
def test_open_three_scans_vertical_and_both_diagonals(stones) -> None:
    board = Board()
    for move in stones:
        board.place(*move, Player.BLACK)
    assert PatternKind.OPEN_THREE in kinds(board)


def test_open_and_closed_two_are_distinct() -> None:
    open_board = Board()
    open_board.place(7, 7, Player.BLACK)
    open_board.place(7, 8, Player.BLACK)
    closed_board = Board()
    closed_board.place(0, 0, Player.BLACK)
    closed_board.place(0, 1, Player.BLACK)

    assert PatternKind.OPEN_TWO in kinds(open_board)
    assert PatternKind.CLOSED_TWO in kinds(closed_board)


def test_all_seven_cell_lines_are_mirror_symmetric_and_deduplicated() -> None:
    matcher = PatternMatcher(line_cache_capacity=10_000)
    line = tuple((7, col) for col in range(4, 11))
    for values in product((0, 1, 2), repeat=7):
        board = Board()
        for (row, col), value in zip(line, values):
            board.grid[row][col] = value
        patterns = matcher._deduplicate_and_suppress(
            matcher._scan_line(board, line, (0, 1), Player.BLACK)
        )

        mirrored = Board()
        for (row, col), value in zip(line, reversed(values)):
            mirrored.grid[row][col] = value
        mirrored_patterns = matcher._deduplicate_and_suppress(
            matcher._scan_line(mirrored, line, (0, 1), Player.BLACK)
        )
        assert Counter(pattern.kind for pattern in patterns) == Counter(
            pattern.kind for pattern in mirrored_patterns
        )
        assert len(patterns) == len({pattern.identity for pattern in patterns})
