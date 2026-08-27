from enum import IntEnum


class Player(IntEnum):
    EMPTY = 0
    BLACK = 1
    WHITE = 2

    @property
    def opponent(self) -> "Player":
        if self == Player.BLACK:
            return Player.WHITE
        if self == Player.WHITE:
            return Player.BLACK
        return Player.EMPTY
