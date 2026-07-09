from __future__ import annotations

import pygame

from gomoku import config
from gomoku.core.enums import Player
from gomoku.core.exceptions import GameOverError, InvalidMoveError
from gomoku.core.game import GomokuGame


def player_label(player: Player | None) -> str:
    if player == Player.BLACK:
        return "Black"
    if player == Player.WHITE:
        return "White"
    return "None"


class PygameGomokuApp:
    def __init__(self) -> None:
        pygame.init()
        self.screen = pygame.display.set_mode(
            (config.WINDOW_WIDTH, config.WINDOW_HEIGHT)
        )
        pygame.display.set_caption("Gomoku")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("Arial", 24)
        self.small_font = pygame.font.SysFont("Arial", 18)
        self.game = GomokuGame(config.BOARD_SIZE)
        self.message = ""

    def run(self) -> None:
        running = True
        while running:
            running = self.handle_events()
            self.draw()
            pygame.display.flip()
            self.clock.tick(config.FPS)

        pygame.quit()

    def handle_events(self) -> bool:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r:
                    self.game.reset()
                    self.message = ""
                elif event.key == pygame.K_u:
                    if self.game.undo():
                        self.message = ""

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                row_col = self.pixel_to_cell(*event.pos)
                if row_col is not None:
                    row, col = row_col
                    try:
                        self.game.make_move(row, col)
                        self.message = ""
                    except InvalidMoveError as exc:
                        self.message = str(exc)
                    except GameOverError:
                        self.message = "Game over"

        return True

    def pixel_to_cell(self, x: int, y: int) -> tuple[int, int] | None:
        col = round((x - config.MARGIN) / config.CELL_SIZE)
        row = round((y - config.MARGIN) / config.CELL_SIZE)

        if not self.game.board.is_inside(row, col):
            return None

        cell_x = config.MARGIN + col * config.CELL_SIZE
        cell_y = config.MARGIN + row * config.CELL_SIZE
        if (
            abs(x - cell_x) <= config.CELL_SIZE // 2
            and abs(y - cell_y) <= config.CELL_SIZE // 2
        ):
            return row, col

        return None

    def draw(self) -> None:
        self.screen.fill(config.BACKGROUND_COLOR)
        self.draw_board()
        self.draw_stones()
        self.draw_status()

    def draw_board(self) -> None:
        board_pixel_size = config.CELL_SIZE * (config.BOARD_SIZE - 1)
        start = config.MARGIN
        end = config.MARGIN + board_pixel_size

        for index in range(config.BOARD_SIZE):
            pos = config.MARGIN + index * config.CELL_SIZE
            pygame.draw.line(
                self.screen,
                config.LINE_COLOR,
                (start, pos),
                (end, pos),
                2,
            )
            pygame.draw.line(
                self.screen,
                config.LINE_COLOR,
                (pos, start),
                (pos, end),
                2,
            )

        for row, col in self.star_points():
            center = self.cell_center(row, col)
            pygame.draw.circle(self.screen, config.LINE_COLOR, center, 4)

    def star_points(self) -> tuple[tuple[int, int], ...]:
        if config.BOARD_SIZE != 15:
            return ()
        return (
            (3, 3),
            (3, 7),
            (3, 11),
            (7, 3),
            (7, 7),
            (7, 11),
            (11, 3),
            (11, 7),
            (11, 11),
        )

    def draw_stones(self) -> None:
        for row in range(self.game.board.size):
            for col in range(self.game.board.size):
                cell = self.game.board.grid[row][col]
                if cell == Player.EMPTY:
                    continue

                center = self.cell_center(row, col)
                color = (
                    config.BLACK_COLOR
                    if cell == Player.BLACK
                    else config.WHITE_COLOR
                )
                pygame.draw.circle(self.screen, color, center, config.STONE_RADIUS)
                pygame.draw.circle(
                    self.screen,
                    config.LINE_COLOR,
                    center,
                    config.STONE_RADIUS,
                    1,
                )

        if self.game.move_history:
            row, col, _player = self.game.move_history[-1]
            pygame.draw.circle(
                self.screen,
                config.LAST_MOVE_COLOR,
                self.cell_center(row, col),
                5,
            )

    def draw_status(self) -> None:
        top = config.WINDOW_WIDTH
        pygame.draw.rect(
            self.screen,
            config.BACKGROUND_COLOR,
            (0, top, config.WINDOW_WIDTH, config.INFO_HEIGHT),
        )

        if self.game.winner is not None:
            status = f"{player_label(self.game.winner)} wins"
            color = config.WIN_COLOR
        elif self.game.game_over:
            status = "Draw"
            color = config.WIN_COLOR
        else:
            status = f"Turn: {player_label(self.game.current_player)}"
            color = config.TEXT_COLOR

        status_surface = self.font.render(status, True, color)
        self.screen.blit(status_surface, (config.MARGIN, top + 18))

        if self.message:
            message_surface = self.small_font.render(
                self.message,
                True,
                config.WIN_COLOR,
            )
            self.screen.blit(message_surface, (config.MARGIN + 180, top + 22))

    def cell_center(self, row: int, col: int) -> tuple[int, int]:
        return (
            config.MARGIN + col * config.CELL_SIZE,
            config.MARGIN + row * config.CELL_SIZE,
        )


def run() -> None:
    PygameGomokuApp().run()
