from __future__ import annotations

from gomoku.core.board import Board
from gomoku.core.enums import Player


WIN_LENGTH = 5
DIRECTIONS = (
    (0, 1),
    (1, 0),
    (1, 1),
    (1, -1),
)


def count_direction(
    board: Board,
    row: int,
    col: int,
    dr: int,
    dc: int,
    player: Player | int,
) -> int:
    player_value = int(Player(player))
    count = 0
    current_row = row + dr
    current_col = col + dc

    while (
        board.is_inside(current_row, current_col)
        and board.grid[current_row][current_col] == player_value
    ):
        count += 1
        current_row += dr
        current_col += dc

    return count


def check_win(board: Board, row: int, col: int, player: Player | int) -> bool:
    if not board.is_inside(row, col):
        return False

    player_value = Player(player)
    if player_value == Player.EMPTY:
        return False

    for dr, dc in DIRECTIONS:
        total = 1
        total += count_direction(board, row, col, dr, dc, player_value)
        total += count_direction(board, row, col, -dr, -dc, player_value)
        if total >= WIN_LENGTH:
            return True

    return False


def get_valid_moves(board: Board) -> list[tuple[int, int]]:
    return [
        (row, col)
        for row in range(board.size)
        for col in range(board.size)
        if board.is_empty(row, col)
    ]
