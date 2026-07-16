from pathlib import Path
import sys


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from gomoku.ai.transposition_table import (
    BoundType,
    TranspositionEntry,
    TranspositionTable,
)


def make_entry(key: int, bound: BoundType, depth: int = 3):
    return TranspositionEntry(key, depth, 42, bound, (7, 7), 1)


def test_transposition_table_preserves_all_bound_types() -> None:
    table = TranspositionTable(10)
    for key, bound in enumerate(
        (BoundType.EXACT, BoundType.LOWER, BoundType.UPPER),
        start=1,
    ):
        table.store(make_entry(key, bound))
        assert table.probe(key).bound == bound


def test_transposition_table_collision_uses_generation_then_depth() -> None:
    table = TranspositionTable(1)
    table.store(make_entry(1, BoundType.LOWER, depth=4))
    table.store(make_entry(2, BoundType.UPPER, depth=3))
    assert table.probe(1) is not None

    table.new_generation()
    replacement = TranspositionEntry(2, 1, 7, BoundType.EXACT, (1, 1), 2)
    table.store(replacement)
    assert table.probe(1) is None
    assert table.probe(2) == replacement
