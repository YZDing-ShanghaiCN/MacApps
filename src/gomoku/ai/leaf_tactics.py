"""Lightweight one-move tactical checks for MCTS leaf nodes.

Bounded and cheap by design (no VCT recursion): only cells from the local
candidate pool are probed, and every probe is a single ``check_win``-style
line scan. The full tactical engine (HardAI VCF/VCT/defense) remains
authoritative; this module only sharpens MCTS leaf values.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable

from gomoku.ai.search_position import SearchPosition
from gomoku.core.enums import Player

Move = tuple[int, int]

_DIRECTIONS = ((0, 1), (1, 0), (1, 1), (1, -1))


@dataclass(frozen=True)
class LeafTactics:
    """One-move tactical facts about a leaf position.

    ``immediate_win``: a move that completes five for ``player``.
    ``opponent_win``: a move that completes five for the opponent (the
    mandatory block cell). ``double_four``: a move creating at least two
    distinct winning cells (double four or open four) — an unstoppable
    win for ``player`` next move.
    """

    immediate_win: Move | None
    opponent_win: Move | None
    double_four: Move | None


def _count_winning_cells(
    position: SearchPosition, move: Move, mover: Player
) -> int:
    """Distinct empty cells on the four lines through ``move`` that would
    complete five for ``mover`` after ``mover`` plays ``move``."""

    row, col = move
    if not position.is_empty(row, col):
        return 0
    position.grid[row][col] = int(mover)
    try:
        completions = 0
        for dr, dc in _DIRECTIONS:
            for step in range(-4, 5):
                if step == 0:
                    continue
                cell = (row + step * dr, col + step * dc)
                if not position.is_empty(*cell):
                    continue
                if position.move_wins(*cell, mover):
                    completions += 1
                    if completions >= 2:
                        return completions
        return completions
    finally:
        position.grid[row][col] = int(Player.EMPTY)


def classify_leaf(
    position: SearchPosition,
    player: Player | int,
    candidate_cells: Iterable[Move],
) -> LeafTactics:
    """Classify one-move tactics for ``player`` restricted to candidates.

    Only empty candidate cells are probed. An immediate win for ``player``
    short-circuits (``player`` moves first); otherwise an opponent win cell
    is reported; otherwise the first move that creates two winning cells.
    """

    mover = Player(player)
    opponent = mover.opponent
    opponent_win: Move | None = None
    for move in sorted(candidate_cells):
        if not position.is_empty(*move):
            continue
        if position.move_wins(*move, mover):
            return LeafTactics(move, None, None)
        if opponent_win is None and position.move_wins(*move, opponent):
            opponent_win = move
    if opponent_win is not None:
        return LeafTactics(None, opponent_win, None)
    for move in sorted(candidate_cells):
        if not position.is_empty(*move):
            continue
        if _count_winning_cells(position, move, mover) >= 2:
            return LeafTactics(None, None, move)
    return LeafTactics(None, None, None)
