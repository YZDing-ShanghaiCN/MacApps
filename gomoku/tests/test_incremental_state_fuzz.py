from pathlib import Path
import random
import sys

import pytest


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from gomoku.ai.candidate_generator import CandidateGenerator
from gomoku.ai.evaluator import StaticEvaluator
from gomoku.ai.normal_ai_config import DEFAULT_NORMAL_AI_CONFIG
from gomoku.ai.pattern_matcher import PatternMatcher
from gomoku.ai.search_position import SearchPosition
from gomoku.ai.zobrist import ZobristTable
from gomoku.core.board import Board
from gomoku.core.enums import Player


@pytest.mark.parametrize("seed", (17, 29, 43, 71))
def test_random_make_undo_matches_full_recomputation(seed: int) -> None:
    rng = random.Random(seed)
    zobrist = ZobristTable(15, 900 + seed)
    position = SearchPosition.from_board(
        Board(),
        Player.BLACK,
        zobrist,
        max_candidate_radius=2,
    )
    incremental_matcher = PatternMatcher()
    incremental = StaticEvaluator(
        DEFAULT_NORMAL_AI_CONFIG,
        incremental_matcher,
    )
    incremental.prepare(position)
    generator = CandidateGenerator(DEFAULT_NORMAL_AI_CONFIG, incremental_matcher)

    for _step in range(36):
        if position.move_stack and (
            len(position.move_stack) >= 18 or rng.random() < 0.32
        ):
            position.undo_move()
        else:
            moves = sorted(position.nearby_empty_moves(2))
            if not moves:
                moves = [
                    (row, col)
                    for row in range(position.size)
                    for col in range(position.size)
                    if position.is_empty(row, col)
                ]
            position.make_move(*rng.choice(moves))

        _assert_matches_full_recomputation(
            position,
            zobrist,
            incremental,
            generator,
        )

    while position.move_stack:
        position.undo_move()
    _assert_matches_full_recomputation(
        position,
        zobrist,
        incremental,
        generator,
    )


def _assert_matches_full_recomputation(
    position: SearchPosition,
    zobrist: ZobristTable,
    incremental: StaticEvaluator,
    generator: CandidateGenerator,
) -> None:
    assert position.hash_key == position.recompute_hash()
    assert position.empty_count == sum(
        cell == int(Player.EMPTY)
        for row in position.grid
        for cell in row
    )
    for radius in (1, 2):
        assert position.nearby_empty_moves(radius) == _brute_nearby(position, radius)

    full_matcher = PatternMatcher()
    full = StaticEvaluator(DEFAULT_NORMAL_AI_CONFIG, full_matcher)
    state = position.evaluation_state
    assert state is not None
    for player in (Player.BLACK, Player.WHITE):
        assert incremental.evaluate(position, player) == full.evaluate(position, player)
        assert {
            pattern.identity for pattern in state.patterns_for(player)
        } == {
            pattern.identity
            for pattern in full_matcher.find_patterns(position, player)
        }

    plain = SearchPosition.from_board(
        position,
        position.current_player,
        zobrist,
        max_candidate_radius=2,
    )
    full_generator = CandidateGenerator(DEFAULT_NORMAL_AI_CONFIG, full_matcher)
    assert generator.generate(position, root=True) == full_generator.generate(
        plain,
        root=True,
    )


def _brute_nearby(position: SearchPosition, radius: int) -> set[tuple[int, int]]:
    if not position.occupied:
        center = position.size // 2
        return {(center, center)}
    return {
        (row, col)
        for row in range(position.size)
        for col in range(position.size)
        if position.is_empty(row, col)
        and any(
            max(abs(row - own_row), abs(col - own_col)) <= radius
            for own_row, own_col in position.occupied
        )
    }
