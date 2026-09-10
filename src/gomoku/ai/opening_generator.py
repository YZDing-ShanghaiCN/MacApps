"""Reproducible generation of diverse legal openings for HardAI arenas.

A fixed handful of openings cannot provide statistical evidence for model
promotion because deterministic engines replay identical games. This module
generates arbitrary numbers of legal, non-terminal, strictly alternating
openings from a seeded RNG: the first stone lands near the center, later
stones stick close to existing stones (falling back to any empty cell), and
every candidate is rejected as soon as any prefix forms a five-in-row.
Color-swap duplicates are deduplicated, since the arena already plays every
opening with both color assignments.
"""

from __future__ import annotations

import random

from gomoku.core.board import Board
from gomoku.core.enums import Player
from gomoku.core.rules import check_win

Move = tuple[int, int]
Opening = tuple[tuple[int, int, Player], ...]

_NEIGHBORHOOD_RADIUS = 2
_MAX_ATTEMPTS_PER_OPENING = 400


def validate_opening(opening: Opening, size: int = 15) -> bool:
    """True iff the opening is legal, alternating and never terminal.

    Rejects out-of-bounds or duplicated cells, a player other than the
    strict BLACK-then-WHITE alternation, and any prefix that already
    contains a five-in-row (terminal) for either player.
    """

    if len(opening) > size * size:
        return False
    board = Board(size)
    for index, (row, col, player) in enumerate(opening):
        expected = Player.BLACK if index % 2 == 0 else Player.WHITE
        if player != expected:
            return False
        if not board.is_inside(row, col) or not board.is_empty(row, col):
            return False
        board.place(row, col, player)
        if check_win(board, row, col, player):
            return False
    return True


def canonical_signature(opening: Opening) -> tuple:
    """Color-normalized signature: two openings match iff one is the other
    with the colors swapped (both are played by the arena anyway)."""

    black = tuple(
        sorted((row, col) for row, col, player in opening if player == Player.BLACK)
    )
    white = tuple(
        sorted((row, col) for row, col, player in opening if player == Player.WHITE)
    )
    return min((black, white), (white, black))


def _random_opening(
    rng: random.Random, length: int, size: int
) -> Opening | None:
    if length <= 0:
        return ()
    center = size // 2
    board = Board(size)
    stones: list[Move] = []
    for index in range(length):
        player = Player.BLACK if index % 2 == 0 else Player.WHITE
        if index == 0:
            candidates = [
                (row, col)
                for row in range(
                    max(0, center - _NEIGHBORHOOD_RADIUS),
                    min(size, center + _NEIGHBORHOOD_RADIUS + 1),
                )
                for col in range(
                    max(0, center - _NEIGHBORHOOD_RADIUS),
                    min(size, center + _NEIGHBORHOOD_RADIUS + 1),
                )
            ]
            move = rng.choice(candidates)
        else:
            nearby = sorted(
                {
                    (row, col)
                    for stone_row, stone_col in stones
                    for row in range(
                        max(0, stone_row - _NEIGHBORHOOD_RADIUS),
                        min(size, stone_row + _NEIGHBORHOOD_RADIUS + 1),
                    )
                    for col in range(
                        max(0, stone_col - _NEIGHBORHOOD_RADIUS),
                        min(size, stone_col + _NEIGHBORHOOD_RADIUS + 1),
                    )
                    if board.is_empty(row, col)
                }
            )
            if nearby:
                move = rng.choice(nearby)
            else:
                empty = [
                    (row, col)
                    for row in range(size)
                    for col in range(size)
                    if board.is_empty(row, col)
                ]
                if not empty:
                    return None
                move = rng.choice(empty)
        board.place(*move, player)
        if check_win(board, move[0], move[1], player):
            return None
        stones.append(move)
    return tuple(
        (row, col, Player.BLACK if index % 2 == 0 else Player.WHITE)
        for index, (row, col) in enumerate(stones)
    )


def generate_openings(
    *,
    seed: int,
    count: int,
    length: int,
    size: int = 15,
    length_max: int | None = None,
) -> tuple[Opening, ...]:
    """Generate ``count`` unique legal openings of length in
    ``[length, length_max or length]``.

    Fully determined by ``(seed, count, length, length_max)``: candidates
    come from the seeded RNG, terminal/illegal ones are rejected and
    color-swap duplicates are deduplicated, so the same arguments always
    return the same tuple.
    """

    if count <= 0:
        return ()
    if length < 0 or (length_max is not None and length_max < length):
        raise ValueError("opening length range must satisfy 0 <= length <= length_max.")
    rng = random.Random(seed)
    openings: list[Opening] = []
    seen: set[tuple] = set()
    attempts = 0
    while len(openings) < count:
        attempts += 1
        if attempts > count * _MAX_ATTEMPTS_PER_OPENING + 100:
            raise RuntimeError(
                f"could not generate {count} valid openings for "
                f"seed={seed} length={length}"
            )
        length_i = (
            length if length_max is None else rng.randint(length, length_max)
        )
        opening = _random_opening(rng, length_i, size)
        if opening is None or not validate_opening(opening, size):
            continue
        signature = canonical_signature(opening)
        if signature in seen:
            continue
        seen.add(signature)
        openings.append(opening)
    return tuple(openings)
