"""Deterministic Zobrist keys for search positions."""

from __future__ import annotations

import random

from gomoku.core.enums import Player


class ZobristTable:
    def __init__(self, size: int, seed: int) -> None:
        if size <= 0:
            raise ValueError("Zobrist board size must be positive.")

        rng = random.Random(seed)
        self.size = size
        self.piece_keys = [
            [
                (rng.getrandbits(64), rng.getrandbits(64))
                for _col in range(size)
            ]
            for _row in range(size)
        ]
        self.side_to_move_key = rng.getrandbits(64)

    def piece_key(self, row: int, col: int, player: Player | int) -> int:
        player_value = Player(player)
        if player_value == Player.EMPTY:
            raise ValueError("Empty cells do not have a Zobrist piece key.")
        return self.piece_keys[row][col][int(player_value) - 1]

    def hash_grid(
        self,
        grid: list[list[int]],
        current_player: Player | int,
    ) -> int:
        key = 0
        for row in range(self.size):
            for col in range(self.size):
                cell = Player(grid[row][col])
                if cell != Player.EMPTY:
                    key ^= self.piece_key(row, col, cell)

        if Player(current_player) == Player.WHITE:
            key ^= self.side_to_move_key
        return key
