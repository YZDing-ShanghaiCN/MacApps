from pathlib import Path
import sys


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from gomoku.ai.evaluator import StaticEvaluator
from gomoku.ai.normal_ai_config import DEFAULT_NORMAL_AI_CONFIG
from gomoku.ai.pattern_matcher import PatternMatcher
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
