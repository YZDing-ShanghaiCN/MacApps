from pathlib import Path
import sys

import pytest


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from gomoku.core.enums import Player
from gomoku.core.exceptions import InvalidMoveError
from gomoku.core.game import GomokuGame


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def test_black_moves_first() -> None:
    game = GomokuGame()

    assert game.current_player == Player.BLACK


def test_valid_move_switches_player() -> None:
    game = GomokuGame()

    game.make_move(7, 7)

    assert game.board.grid[7][7] == Player.BLACK
    assert game.current_player == Player.WHITE


def test_invalid_move_raises_error() -> None:
    game = GomokuGame()
    game.make_move(7, 7)

    with pytest.raises(InvalidMoveError):
        game.make_move(7, 7)


def test_game_over_after_win() -> None:
    game = GomokuGame()
    moves = [
        (0, 0),
        (1, 0),
        (0, 1),
        (1, 1),
        (0, 2),
        (1, 2),
        (0, 3),
        (1, 3),
        (0, 4),
    ]

    for row, col in moves:
        game.make_move(row, col)

    assert game.game_over
    assert game.winner == Player.BLACK
    assert game.winning_line == tuple((0, col) for col in range(5))


def test_reset_restores_initial_state() -> None:
    game = GomokuGame()
    game.make_move(7, 7)

    game.reset()

    assert game.current_player == Player.BLACK
    assert game.winner is None
    assert not game.game_over
    assert game.move_history == []
    assert all(cell == Player.EMPTY for row in game.board.grid for cell in row)


def test_undo_reverts_one_move() -> None:
    game = GomokuGame()
    game.make_move(7, 7)

    undone = game.undo()

    assert undone
    assert game.board.grid[7][7] == Player.EMPTY
    assert game.current_player == Player.BLACK
    assert game.move_history == []


def test_timer_tracks_each_players_turn() -> None:
    clock = FakeClock()
    game = GomokuGame(clock=clock)

    assert game.start_timer()
    clock.advance(4.5)
    game.make_move(7, 7)
    clock.advance(2.25)
    game.make_move(7, 8)

    state = game.get_state()
    assert state["timer_running"] is True
    assert state["time_spent"] == {"black": 4.5, "white": 2.25}


def test_timer_stops_when_game_ends() -> None:
    clock = FakeClock()
    game = GomokuGame(clock=clock)
    game.start_timer()
    moves = [
        (0, 0),
        (1, 0),
        (0, 1),
        (1, 1),
        (0, 2),
        (1, 2),
        (0, 3),
        (1, 3),
        (0, 4),
    ]

    for row, col in moves:
        clock.advance(1)
        game.make_move(row, col)

    elapsed_at_win = game.get_state()["time_spent"]
    clock.advance(10)

    assert game.timer_running is False
    assert game.get_state()["time_spent"] == elapsed_at_win


def test_undo_keeps_time_already_spent() -> None:
    clock = FakeClock()
    game = GomokuGame(clock=clock)
    game.start_timer()
    clock.advance(5)
    game.make_move(7, 7)
    clock.advance(3)

    assert game.undo()
    assert game.get_state()["time_spent"] == {"black": 5.0, "white": 3.0}
    assert game.timer_running is True


def test_undo_after_a_win_resumes_an_already_started_timer() -> None:
    clock = FakeClock()
    game = GomokuGame(clock=clock)
    game.start_timer()
    moves = [
        (0, 0),
        (1, 0),
        (0, 1),
        (1, 1),
        (0, 2),
        (1, 2),
        (0, 3),
        (1, 3),
        (0, 4),
    ]

    for row, col in moves:
        clock.advance(1)
        game.make_move(row, col)

    elapsed_at_win = game.get_state()["time_spent"]
    assert game.undo()
    clock.advance(2)

    assert game.timer_running is True
    assert game.get_state()["time_spent"] == {
        "black": elapsed_at_win["black"] + 2,
        "white": elapsed_at_win["white"],
    }
