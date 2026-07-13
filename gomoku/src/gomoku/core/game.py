from __future__ import annotations

import time
from collections.abc import Callable

from gomoku.config import BOARD_SIZE
from gomoku.core.board import Board
from gomoku.core.enums import Player
from gomoku.core.exceptions import GameOverError
from gomoku.core.rules import find_winning_line


class GomokuGame:
    """Core game state manager with no UI or network dependencies."""

    def __init__(
        self,
        size: int = BOARD_SIZE,
        clock: Callable[[], float] = time.monotonic,
        starting_player: Player | int = Player.BLACK,
    ) -> None:
        self.board = Board(size)
        self._clock = clock
        self.starting_player = self._validate_starting_player(starting_player)
        self.current_player = self.starting_player
        self.winner: Player | None = None
        self.game_over = False
        self.move_history: list[tuple[int, int, Player]] = []
        self.winning_line: tuple[tuple[int, int], ...] = ()
        self.timer_running = False
        self._timer_started = False
        self._turn_started_at: float | None = None
        self._elapsed_seconds = {
            Player.BLACK: 0.0,
            Player.WHITE: 0.0,
        }

    def start_timer(self) -> bool:
        """Start cumulative turn timing for a game that is ready to play."""

        if self.timer_running or self.game_over:
            return False

        self.timer_running = True
        self._timer_started = True
        self._turn_started_at = self._clock()
        return True

    def make_move(self, row: int, col: int) -> dict:
        if self.game_over:
            raise GameOverError("Cannot make a move after the game is over.")

        player = self.current_player
        self.board.place(row, col, player)
        self.move_history.append((row, col, player))
        self._settle_current_turn()

        winning_line = find_winning_line(self.board, row, col, player)
        if winning_line is not None:
            self.winner = player
            self.winning_line = winning_line
            self.game_over = True
            self._stop_timer()
        elif self.board.is_full():
            self.game_over = True
            self._stop_timer()
        else:
            self.switch_player()

        return self.get_state()

    def undo(self) -> bool:
        if not self.move_history:
            return False

        resume_timer = self.game_over and self._timer_started
        self._settle_current_turn()
        row, col, player = self.move_history.pop()
        self.board.grid[row][col] = int(Player.EMPTY)
        self.current_player = player
        self.winner = None
        self.winning_line = ()
        self.game_over = False
        if resume_timer:
            self.timer_running = True
            self._turn_started_at = self._clock()
        return True

    def reset(self, starting_player: Player | int | None = None) -> None:
        if starting_player is not None:
            self.starting_player = self._validate_starting_player(starting_player)

        self.board.reset()
        self.current_player = self.starting_player
        self.winner = None
        self.game_over = False
        self.move_history.clear()
        self.winning_line = ()
        self.timer_running = False
        self._timer_started = False
        self._turn_started_at = None
        self._elapsed_seconds = {
            Player.BLACK: 0.0,
            Player.WHITE: 0.0,
        }

    def get_state(self) -> dict:
        return {
            "board": self.board.to_list(),
            "size": self.board.size,
            "current_player": int(self.current_player),
            "winner": int(self.winner) if self.winner is not None else None,
            "game_over": self.game_over,
            "winning_line": [
                {"row": row, "col": col}
                for row, col in self.winning_line
            ],
            "timer_running": self.timer_running,
            "time_spent": {
                "black": self.elapsed_seconds(Player.BLACK),
                "white": self.elapsed_seconds(Player.WHITE),
            },
            "move_history": [
                {"row": row, "col": col, "player": int(player)}
                for row, col, player in self.move_history
            ],
        }

    def switch_player(self) -> None:
        self.current_player = self.current_player.opponent

    def elapsed_seconds(self, player: Player | int) -> float:
        """Return a player's accumulated thinking time without mutating state."""

        player_value = Player(player)
        elapsed = self._elapsed_seconds[player_value]
        if (
            self.timer_running
            and player_value == self.current_player
            and self._turn_started_at is not None
        ):
            elapsed += max(0.0, self._clock() - self._turn_started_at)
        return round(elapsed, 3)

    def _settle_current_turn(self) -> None:
        if not self.timer_running or self._turn_started_at is None:
            return

        now = self._clock()
        self._elapsed_seconds[self.current_player] += max(
            0.0,
            now - self._turn_started_at,
        )
        self._turn_started_at = now

    def _stop_timer(self) -> None:
        self.timer_running = False
        self._turn_started_at = None

    def _validate_starting_player(self, player: Player | int) -> Player:
        player_value = Player(player)
        if player_value == Player.EMPTY:
            raise ValueError("The starting player must be black or white.")
        return player_value
