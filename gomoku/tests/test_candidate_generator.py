from dataclasses import replace
from pathlib import Path
import sys


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from gomoku.ai.candidate_generator import CandidateGenerator
from gomoku.ai.normal_ai_config import DEFAULT_NORMAL_AI_CONFIG
from gomoku.ai.pattern_matcher import PatternMatcher
from gomoku.ai.search_position import SearchPosition
from gomoku.ai.zobrist import ZobristTable
from gomoku.core.board import Board
from gomoku.core.enums import Player


def position_from(board, player=Player.WHITE):
    return SearchPosition.from_board(board, player, ZobristTable(board.size, 5))


def test_empty_board_uses_center() -> None:
    config = DEFAULT_NORMAL_AI_CONFIG
    generator = CandidateGenerator(config, PatternMatcher())
    moves = generator.generate(position_from(Board(), Player.BLACK), root=True)
    assert moves == [(7, 7)]


def test_immediate_wins_and_blocks_ignore_quiet_candidate_limit() -> None:
    board = Board()
    for col in range(4, 8):
        board.place(7, col, Player.BLACK)
    for row in range(3, 7):
        board.place(row, 10, Player.WHITE)
    config = replace(
        DEFAULT_NORMAL_AI_CONFIG,
        root_max_quiet_candidates=1,
        inner_max_quiet_candidates=1,
    )
    generator = CandidateGenerator(config, PatternMatcher())
    moves = generator.generate(position_from(board, Player.WHITE), root=True)

    assert {(2, 10), (7, 3), (7, 8)}.issubset(set(moves))
    assert len(moves) == len(set(moves))


def test_candidate_order_is_reproducible() -> None:
    board = Board()
    board.place(7, 7, Player.BLACK)
    generator = CandidateGenerator(DEFAULT_NORMAL_AI_CONFIG, PatternMatcher())
    position = position_from(board)
    assert generator.generate(position, root=True) == generator.generate(
        position,
        root=True,
    )


def test_crossing_double_threat_point_is_ranked_first() -> None:
    board = Board()
    for col in (4, 5, 6):
        board.place(7, col, Player.WHITE)
    for row in (4, 5, 6):
        board.place(row, 7, Player.WHITE)
    board.place(10, 10, Player.BLACK)
    generator = CandidateGenerator(DEFAULT_NORMAL_AI_CONFIG, PatternMatcher())

    moves = generator.generate(position_from(board, Player.WHITE), root=True)
    assert moves[0] == (7, 7)
