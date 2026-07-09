from __future__ import annotations

from gomoku.config import BOARD_SIZE
from gomoku.core.board import Board
from gomoku.core.enums import Player
from gomoku.core.exceptions import GameOverError
from gomoku.core.rules import check_win


class GomokuGame:
    """Core game state manager with no UI or network dependencies."""

    def __init__(self, size: int = BOARD_SIZE) -> None:
        self.board = Board(size)
        self.current_player = Player.BLACK
        self.winner: Player | None = None
        self.game_over = False
        self.move_history: list[tuple[int, int, Player]] = []

    def make_move(self, row: int, col: int) -> dict:
        if self.game_over:
            raise GameOverError("Cannot make a move after the game is over.")

        player = self.current_player
        self.board.place(row, col, player)
        self.move_history.append((row, col, player))

        if check_win(self.board, row, col, player):
            self.winner = player
            self.game_over = True
        elif self.board.is_full():
            self.game_over = True
        else:
            self.switch_player()

        return self.get_state()

    def undo(self) -> bool:
        if not self.move_history:
            return False

        row, col, player = self.move_history.pop()
        self.board.grid[row][col] = int(Player.EMPTY)
        self.current_player = player
        self.winner = None
        self.game_over = False
        return True

    def reset(self) -> None:
        self.board.reset()
        self.current_player = Player.BLACK
        self.winner = None
        self.game_over = False
        self.move_history.clear()

    def get_state(self) -> dict:
        return {
            "board": self.board.to_list(),
            "size": self.board.size,
            "current_player": int(self.current_player),
            "winner": int(self.winner) if self.winner is not None else None,
            "game_over": self.game_over,
            "move_history": [
                {"row": row, "col": col, "player": int(player)}
                for row, col, player in self.move_history
            ],
        }

    def switch_player(self) -> None:
        self.current_player = self.current_player.opponent
