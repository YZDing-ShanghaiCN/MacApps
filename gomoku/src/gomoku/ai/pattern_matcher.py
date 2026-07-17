"""Coordinate-aware Gomoku pattern recognition for NormalAI."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import Enum

from gomoku.core.board import Board
from gomoku.core.enums import Player
from gomoku.core.rules import DIRECTIONS, WIN_LENGTH


Move = tuple[int, int]


class PatternKind(str, Enum):
    FIVE = "five"
    OPEN_FOUR = "open_four"
    CLOSED_FOUR = "closed_four"
    OPEN_THREE = "open_three"
    JUMP_THREE = "jump_three"
    CLOSED_THREE = "closed_three"
    OPEN_TWO = "open_two"
    CLOSED_TWO = "closed_two"


PATTERN_SEVERITY = {
    PatternKind.FIVE: 8,
    PatternKind.OPEN_FOUR: 7,
    PatternKind.CLOSED_FOUR: 6,
    PatternKind.OPEN_THREE: 5,
    PatternKind.JUMP_THREE: 4,
    PatternKind.CLOSED_THREE: 3,
    PatternKind.OPEN_TWO: 2,
    PatternKind.CLOSED_TWO: 1,
}


@dataclass(frozen=True)
class Pattern:
    kind: PatternKind
    direction: tuple[int, int]
    stones: frozenset[Move]
    key_empties: frozenset[Move]

    @property
    def identity(self) -> tuple:
        return (
            self.kind,
            self.direction,
            self.stones,
            self.key_empties,
        )


class PatternMatcher:
    """Find tactical shapes without counting overlapping windows twice."""

    def __init__(self, line_cache_capacity: int = 0) -> None:
        self.line_cache_capacity = max(0, line_cache_capacity)
        self._line_cache: OrderedDict[tuple, tuple[Pattern, ...]] = OrderedDict()

    def find_patterns(
        self,
        board: Board,
        player: Player | int,
        timeout_check: Callable[[], None] | None = None,
    ) -> tuple[Pattern, ...]:
        player_value = Player(player)
        if player_value == Player.EMPTY:
            return ()

        patterns: list[Pattern] = []
        for direction in DIRECTIONS:
            for line in self._direction_lines(board, direction):
                if timeout_check is not None:
                    timeout_check()
                patterns.extend(
                    self._scan_line(board, line, direction, player_value)
                )
        return self._deduplicate_and_suppress(patterns)

    def find_patterns_through_move(
        self,
        board: Board,
        player: Player | int,
        move: Move,
        timeout_check: Callable[[], None] | None = None,
    ) -> tuple[Pattern, ...]:
        player_value = Player(player)
        row, col = move
        if player_value == Player.EMPTY or not board.is_inside(row, col):
            return ()

        patterns: list[Pattern] = []
        for direction in DIRECTIONS:
            if timeout_check is not None:
                timeout_check()
            line = self._line_through(board, move, direction)
            patterns.extend(self._scan_line(board, line, direction, player_value))
        return tuple(
            pattern
            for pattern in self._deduplicate_and_suppress(patterns)
            if move in pattern.stones
        )

    def _direction_lines(
        self,
        board: Board,
        direction: tuple[int, int],
    ) -> Iterable[tuple[Move, ...]]:
        dr, dc = direction
        for row in range(board.size):
            for col in range(board.size):
                previous_row = row - dr
                previous_col = col - dc
                if board.is_inside(previous_row, previous_col):
                    continue
                line: list[Move] = []
                current_row, current_col = row, col
                while board.is_inside(current_row, current_col):
                    line.append((current_row, current_col))
                    current_row += dr
                    current_col += dc
                if len(line) >= 2:
                    yield tuple(line)

    def _line_through(
        self,
        board: Board,
        move: Move,
        direction: tuple[int, int],
    ) -> tuple[Move, ...]:
        dr, dc = direction
        row, col = move
        while board.is_inside(row - dr, col - dc):
            row -= dr
            col -= dc
        line: list[Move] = []
        while board.is_inside(row, col):
            line.append((row, col))
            row += dr
            col += dc
        return tuple(line)

    def _scan_line(
        self,
        board: Board,
        line: tuple[Move, ...],
        direction: tuple[int, int],
        player: Player,
    ) -> list[Pattern]:
        own = int(player)
        values = [board.grid[row][col] for row, col in line]
        cache_key = (direction, line, own, tuple(values))
        cached = self._line_cache.get(cache_key)
        if cached is not None:
            self._line_cache.move_to_end(cache_key)
            return list(cached)
        if values.count(own) < 2:
            self._remember_line(cache_key, ())
            return []
        patterns: list[Pattern] = []

        # A maximal run represents one five pattern, including overlines.
        run_start = 0
        while run_start < len(values):
            if values[run_start] != own:
                run_start += 1
                continue
            run_end = run_start
            while run_end + 1 < len(values) and values[run_end + 1] == own:
                run_end += 1
            if run_end - run_start + 1 >= 5:
                patterns.append(
                    Pattern(
                        PatternKind.FIVE,
                        direction,
                        frozenset(line[run_start : run_end + 1]),
                        frozenset(),
                    )
                )
            run_start = run_end + 1

        four_groups = self._groups_with_counts(values, line, own, stone_count=4)
        for stones, key_indexes in four_groups.items():
            key_moves = frozenset(line[index] for index in key_indexes)
            kind = (
                PatternKind.OPEN_FOUR
                if len(key_indexes) >= 2
                else PatternKind.CLOSED_FOUR
            )
            patterns.append(Pattern(kind, direction, stones, key_moves))

        three_groups = self._groups_with_counts(values, line, own, stone_count=3)
        for stones, window_empty_indexes in three_groups.items():
            creating_moves: set[int] = set()
            open_four_moves: set[int] = set()
            stone_indexes = {line.index(move) for move in stones}
            for empty_index, value in enumerate(values):
                if value != int(Player.EMPTY):
                    continue
                test_values = values.copy()
                test_values[empty_index] = own
                resulting_fours = self._index_groups_with_counts(
                    test_values,
                    own,
                    stone_count=4,
                )
                for resulting_stones, winning_indexes in resulting_fours.items():
                    if not stone_indexes.issubset(resulting_stones):
                        continue
                    creating_moves.add(empty_index)
                    if len(winning_indexes) >= 2:
                        open_four_moves.add(empty_index)

            if not creating_moves:
                continue
            indexes = sorted(stone_indexes)
            is_contiguous = indexes[-1] - indexes[0] + 1 == len(indexes)
            if is_contiguous and len(open_four_moves) >= 2:
                kind = PatternKind.OPEN_THREE
                keys = open_four_moves
            elif not is_contiguous and open_four_moves:
                kind = PatternKind.JUMP_THREE
                keys = open_four_moves
            else:
                kind = PatternKind.CLOSED_THREE
                keys = creating_moves or window_empty_indexes
            patterns.append(
                Pattern(
                    kind,
                    direction,
                    stones,
                    frozenset(line[index] for index in keys),
                )
            )

        two_groups = self._groups_with_counts(values, line, own, stone_count=2)
        for stones, window_empty_indexes in two_groups.items():
            stone_indexes = sorted(line.index(move) for move in stones)
            left_space = stone_indexes[0] > 0 and values[stone_indexes[0] - 1] == 0
            right_space = (
                stone_indexes[-1] + 1 < len(values)
                and values[stone_indexes[-1] + 1] == 0
            )
            span = stone_indexes[-1] - stone_indexes[0] + 1
            kind = (
                PatternKind.OPEN_TWO
                if left_space and right_space and span <= 4
                else PatternKind.CLOSED_TWO
            )
            patterns.append(
                Pattern(
                    kind,
                    direction,
                    stones,
                    frozenset(line[index] for index in window_empty_indexes),
                )
            )
        self._remember_line(cache_key, tuple(patterns))
        return patterns

    def _remember_line(
        self,
        key: tuple,
        patterns: tuple[Pattern, ...],
    ) -> None:
        if self.line_cache_capacity <= 0:
            return
        self._line_cache[key] = patterns
        self._line_cache.move_to_end(key)
        while len(self._line_cache) > self.line_cache_capacity:
            self._line_cache.popitem(last=False)

    def _groups_with_counts(
        self,
        values: list[int],
        line: tuple[Move, ...],
        own: int,
        stone_count: int,
    ) -> dict[frozenset[Move], set[int]]:
        index_groups = self._index_groups_with_counts(values, own, stone_count)
        return {
            frozenset(line[index] for index in stone_indexes): set(empty_indexes)
            for stone_indexes, empty_indexes in index_groups.items()
        }

    def _index_groups_with_counts(
        self,
        values: list[int],
        own: int,
        stone_count: int,
    ) -> dict[frozenset[int], set[int]]:
        groups: dict[frozenset[int], set[int]] = {}
        if len(values) < WIN_LENGTH:
            return groups
        for start in range(len(values) - WIN_LENGTH + 1):
            window = values[start : start + WIN_LENGTH]
            if any(value not in (int(Player.EMPTY), own) for value in window):
                continue
            stone_indexes = frozenset(
                start + offset
                for offset, value in enumerate(window)
                if value == own
            )
            if len(stone_indexes) != stone_count:
                continue
            empty_indexes = {
                start + offset
                for offset, value in enumerate(window)
                if value == int(Player.EMPTY)
            }
            groups.setdefault(stone_indexes, set()).update(empty_indexes)
        return groups

    def _deduplicate_and_suppress(
        self,
        patterns: Iterable[Pattern],
    ) -> tuple[Pattern, ...]:
        merged: dict[tuple, set[Move]] = {}
        for pattern in patterns:
            base_key = (pattern.kind, pattern.direction, pattern.stones)
            merged.setdefault(base_key, set()).update(pattern.key_empties)

        unique = [
            Pattern(kind, direction, stones, frozenset(key_empties))
            for (kind, direction, stones), key_empties in merged.items()
        ]
        kept: list[Pattern] = []
        for pattern in unique:
            dominated = any(
                other.direction == pattern.direction
                and PATTERN_SEVERITY[other.kind] > PATTERN_SEVERITY[pattern.kind]
                and pattern.stones.issubset(other.stones)
                for other in unique
            )
            if not dominated:
                kept.append(pattern)

        return tuple(
            sorted(
                kept,
                key=lambda pattern: (
                    -PATTERN_SEVERITY[pattern.kind],
                    DIRECTIONS.index(pattern.direction),
                    tuple(sorted(pattern.stones)),
                    tuple(sorted(pattern.key_empties)),
                ),
            )
        )
