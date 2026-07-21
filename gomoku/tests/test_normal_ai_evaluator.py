from pathlib import Path
import sys
from dataclasses import replace


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from gomoku.ai.evaluator import StaticEvaluator
from gomoku.ai.normal_ai_config import DEFAULT_NORMAL_AI_CONFIG
from gomoku.ai.pattern_matcher import PatternMatcher
from gomoku.ai.search_position import SearchPosition
from gomoku.ai.zobrist import ZobristTable
from gomoku.core.board import Board
from gomoku.core.enums import Player


def evaluator():
    return StaticEvaluator(DEFAULT_NORMAL_AI_CONFIG, PatternMatcher())


def test_evaluation_rewards_own_threat_and_penalizes_opponent_threat() -> None:
    own = Board()
    opponent = Board()
    for col in range(5, 8):
        own.place(7, col, Player.WHITE)
        opponent.place(7, col, Player.BLACK)

    assert evaluator().evaluate(own, Player.WHITE) > 0
    assert evaluator().evaluate(opponent, Player.WHITE) < 0
    assert abs(evaluator().evaluate(opponent, Player.WHITE)) > evaluator().evaluate(
        own,
        Player.WHITE,
    )


def test_crossing_threat_receives_double_threat_bonus() -> None:
    single = Board()
    cross = Board()
    for col in range(5, 8):
        single.place(7, col, Player.WHITE)
        cross.place(7, col, Player.WHITE)
    for row in range(5, 8):
        cross.place(row, 7, Player.WHITE) if row != 7 else None

    assert evaluator().evaluate(cross, Player.WHITE) > evaluator().evaluate(
        single,
        Player.WHITE,
    ) + DEFAULT_NORMAL_AI_CONFIG.double_threat_bonus


def test_defense_pattern_scores_can_be_tuned_independently() -> None:
    board = Board()
    for col in range(5, 8):
        board.place(7, col, Player.BLACK)
    defense_scores = dict(DEFAULT_NORMAL_AI_CONFIG.defense_pattern_scores)
    defense_scores["open_three"] *= 2
    tuned_config = replace(
        DEFAULT_NORMAL_AI_CONFIG,
        defense_pattern_scores=defense_scores,
    )
    tuned = StaticEvaluator(tuned_config, PatternMatcher()).evaluate(
        board,
        Player.WHITE,
    )
    normal = evaluator().evaluate(board, Player.WHITE)
    assert tuned < normal


def test_center_bonus_decays_to_zero_in_late_game() -> None:
    config = replace(
        DEFAULT_NORMAL_AI_CONFIG,
        center_bonus_full_until_moves=1,
        center_bonus_zero_after_moves=3,
    )
    static = StaticEvaluator(config, PatternMatcher())
    early = Board()
    early.place(7, 7, Player.WHITE)
    late = Board()
    late.place(7, 7, Player.WHITE)
    late.place(0, 0, Player.BLACK)
    late.place(0, 1, Player.BLACK)
    assert static._position_score(early, Player.WHITE) > 0
    assert static._position_score(late, Player.WHITE) == 0


def test_incremental_evaluation_matches_full_scan_and_restores_after_undo() -> None:
    board = Board()
    for row, col, player in (
        (7, 7, Player.BLACK),
        (7, 8, Player.WHITE),
        (8, 8, Player.BLACK),
        (6, 6, Player.WHITE),
    ):
        board.place(row, col, player)
    position = SearchPosition.from_board(
        board,
        Player.BLACK,
        ZobristTable(board.size, 303),
    )
    incremental = StaticEvaluator(DEFAULT_NORMAL_AI_CONFIG, PatternMatcher())
    incremental.prepare(position)
    full_scan = StaticEvaluator(DEFAULT_NORMAL_AI_CONFIG, PatternMatcher())
    original_scores = {
        player: incremental.evaluate(position, player)
        for player in (Player.BLACK, Player.WHITE)
    }

    for move in ((8, 7), (6, 8), (9, 7), (5, 8)):
        position.make_move(*move)
        for player in (Player.BLACK, Player.WHITE):
            assert incremental.evaluate(position, player) == full_scan.evaluate(
                position,
                player,
            )

    for _ in range(4):
        position.undo_move()

    assert {
        player: incremental.evaluate(position, player)
        for player in (Player.BLACK, Player.WHITE)
    } == original_scores
    assert position.grid == board.grid
