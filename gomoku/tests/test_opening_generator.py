from pathlib import Path
import sys


SRC_DIR = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SRC_DIR))

from gomoku.ai.opening_generator import (  # noqa: E402
    canonical_signature,
    generate_openings,
    validate_opening,
)
from gomoku.core.enums import Player  # noqa: E402


def test_generated_openings_are_valid() -> None:
    openings = generate_openings(seed=0, count=20, length=6)

    assert len(openings) == 20
    for opening in openings:
        assert validate_opening(opening, 15)


def test_generation_is_deterministic() -> None:
    first = generate_openings(seed=42, count=8, length=4)
    second = generate_openings(seed=42, count=8, length=4)

    assert first == second


def test_different_seeds_generate_different_openings() -> None:
    first = generate_openings(seed=1, count=8, length=4)
    second = generate_openings(seed=2, count=8, length=4)

    assert first != second


def test_generated_openings_are_unique_up_to_color_swap() -> None:
    openings = generate_openings(seed=3, count=30, length=6)

    signatures = {canonical_signature(opening) for opening in openings}
    assert len(signatures) == len(openings)


def test_validate_rejects_terminal_opening() -> None:
    non_terminal = tuple(
        (7, col, Player.BLACK if col % 2 == 1 else Player.WHITE)
        for col in range(3, 8)
    )
    assert validate_opening(non_terminal, 15) is True

    # Strict alternation reaching five black stones in a row: terminal.
    terminal = (
        (7, 3, Player.BLACK),
        (7, 8, Player.WHITE),
        (7, 4, Player.BLACK),
        (7, 9, Player.WHITE),
        (7, 5, Player.BLACK),
        (7, 10, Player.WHITE),
        (7, 6, Player.BLACK),
        (7, 11, Player.WHITE),
        (7, 7, Player.BLACK),
    )
    assert validate_opening(terminal, 15) is False

    non_alternating = tuple((7, col, Player.BLACK) for col in range(3, 8))
    assert validate_opening(non_alternating, 15) is False


def test_validate_rejects_illegal_cells() -> None:
    assert validate_opening(((-1, 3, Player.BLACK),), 15) is False
    assert validate_opening(((15, 3, Player.BLACK),), 15) is False
    assert validate_opening(
        ((7, 7, Player.BLACK), (7, 7, Player.WHITE)), 15
    ) is False


def test_validate_rejects_non_alternating_or_wrong_starter() -> None:
    assert validate_opening(
        ((7, 7, Player.BLACK), (7, 8, Player.BLACK)), 15
    ) is False
    assert validate_opening(((7, 7, Player.WHITE),), 15) is False
    assert validate_opening(
        ((7, 7, Player.BLACK), (7, 8, Player.WHITE)), 15
    ) is True


def test_length_range_is_respected() -> None:
    openings = generate_openings(
        seed=5, count=12, length=2, length_max=5
    )

    assert len(openings) == 12
    for opening in openings:
        assert 2 <= len(opening) <= 5


def test_zero_count_and_empty_length() -> None:
    assert generate_openings(seed=0, count=0, length=4) == ()
    empty = generate_openings(seed=0, count=1, length=0)
    assert empty == ((),)


def test_canonical_signature_ignores_color_swap() -> None:
    opening = (
        (7, 7, Player.BLACK),
        (7, 8, Player.WHITE),
        (6, 7, Player.BLACK),
    )
    swapped = (
        (7, 7, Player.WHITE),
        (7, 8, Player.BLACK),
        (6, 7, Player.WHITE),
    )

    assert canonical_signature(opening) == canonical_signature(swapped)
