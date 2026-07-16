"""Independent, reversible board state used only by NormalAI searches."""

from __future__ import annotations

from dataclasses import dataclass

from gomoku.ai.zobrist import ZobristTable
from gomoku.core.board import Board
from gomoku.core.enums import Player
from gomoku.core.exceptions import InvalidMoveError
from gomoku.core.rules import check_win


@dataclass(frozen=True)
class SearchMove:
    row: int
    col: int
    player: Player
    previous_hash: int


class SearchPosition(Board):
    """A deep-copied Board with efficient move, undo and incremental hash."""

    def __init__(
        self,
        grid: list[list[int]],
        current_player: Player | int,
        zobrist: ZobristTable,
    ) -> None:
        size = len(grid)
        if size != zobrist.size or any(len(row) != size for row in grid):
            raise ValueError("Search grid and Zobrist table sizes must match.")

        super().__init__(size)
        self.grid = [row.copy() for row in grid]
        self.current_player = Player(current_player)
        if self.current_player == Player.EMPTY:
            raise ValueError("SearchPosition requires a non-empty current player.")
        self.zobrist = zobrist
        self.hash_key = zobrist.hash_grid(self.grid, self.current_player)
        self.move_stack: list[SearchMove] = []
        self.empty_count = sum(
            cell == int(Player.EMPTY)
            for row in self.grid
            for cell in row
        )

    @classmethod
    def from_board(
        cls,
        board: Board,
        current_player: Player | int,
        zobrist: ZobristTable,
    ) -> "SearchPosition":
        return cls(board.to_list(), current_player, zobrist)

    @property
    def last_move(self) -> SearchMove | None:
        return self.move_stack[-1] if self.move_stack else None

    def make_move(self, row: int, col: int) -> None:
        if not self.is_inside(row, col):
            raise InvalidMoveError(f"Move ({row}, {col}) is outside the board.")
        if not self.is_empty(row, col):
            raise InvalidMoveError(f"Cell ({row}, {col}) is already occupied.")

        player = self.current_player
        previous_hash = self.hash_key
        self.grid[row][col] = int(player)
        self.hash_key ^= self.zobrist.piece_key(row, col, player)
        self.current_player = player.opponent
        self.hash_key ^= self.zobrist.side_to_move_key
        self.empty_count -= 1
        self.move_stack.append(SearchMove(row, col, player, previous_hash))

    def undo_move(self) -> SearchMove:
        if not self.move_stack:
            raise RuntimeError("Cannot undo an empty search move stack.")

        move = self.move_stack.pop()
        self.current_player = move.player
        self.grid[move.row][move.col] = int(Player.EMPTY)
        self.empty_count += 1

        # Perform the inverse XOR operations, then verify against the snapshot.
        self.hash_key ^= self.zobrist.side_to_move_key
        self.hash_key ^= self.zobrist.piece_key(move.row, move.col, move.player)
        if self.hash_key != move.previous_hash:
            raise RuntimeError("Zobrist hash failed to restore after undo.")
        return move

    def move_wins(self, row: int, col: int, player: Player | int) -> bool:
        """Test a hypothetical move without changing turn, history or hash."""

        if not self.is_empty(row, col):
            return False
        player_value = Player(player)
        if player_value == Player.EMPTY:
            return False

        self.grid[row][col] = int(player_value)
        try:
            return check_win(self, row, col, player_value)
        finally:
            self.grid[row][col] = int(Player.EMPTY)

    def recompute_hash(self) -> int:
        return self.zobrist.hash_grid(self.grid, self.current_player)
