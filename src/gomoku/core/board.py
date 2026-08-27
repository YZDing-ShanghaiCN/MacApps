from __future__ import annotations

from gomoku.config import BOARD_SIZE
from gomoku.core.enums import Player
from gomoku.core.exceptions import InvalidMoveError


class Board:
    """Two-dimensional Gomoku board.

    The board stores JSON-friendly integer values:
    0 = empty, 1 = black, 2 = white.
    """

    def __init__(self, size: int = BOARD_SIZE) -> None:
        if size <= 0:
            raise ValueError("Board size must be positive.")
        self.size = size
        self.grid: list[list[int]] = []
        self.reset()

    def is_inside(self, row: int, col: int) -> bool:
        return 0 <= row < self.size and 0 <= col < self.size

    def is_empty(self, row: int, col: int) -> bool:
        return self.is_inside(row, col) and self.grid[row][col] == Player.EMPTY

    def place(self, row: int, col: int, player: Player | int) -> None:
        if not self.is_inside(row, col):
            raise InvalidMoveError(f"Move ({row}, {col}) is outside the board.")

        if not self.is_empty(row, col):
            raise InvalidMoveError(f"Cell ({row}, {col}) is already occupied.")

        try:
            player_value = Player(player)
        except ValueError as exc:
            raise InvalidMoveError(f"Unknown player value: {player}.") from exc

        if player_value == Player.EMPTY:
            raise InvalidMoveError("Cannot place an empty cell.")

        self.grid[row][col] = int(player_value)

    def reset(self) -> None:
        self.grid = [
            [int(Player.EMPTY) for _ in range(self.size)]
            for _ in range(self.size)
        ]

    def is_full(self) -> bool:
        return all(cell != Player.EMPTY for row in self.grid for cell in row)

    def to_list(self) -> list[list[int]]:
        return [row.copy() for row in self.grid]
