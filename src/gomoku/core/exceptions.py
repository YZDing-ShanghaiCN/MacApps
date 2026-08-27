class InvalidMoveError(Exception):
    """Raised when a move is outside the board or targets an occupied cell."""


class GameOverError(Exception):
    """Raised when trying to play after the game has already ended."""
