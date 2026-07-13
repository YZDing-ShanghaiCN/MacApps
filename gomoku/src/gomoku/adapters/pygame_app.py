from __future__ import annotations

import pygame

from gomoku import config
from gomoku.ai.simple_ai import SimpleAI
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
        self.mode = config.DEFAULT_MODE
        self.ai_player = Player.WHITE
        self.ai = SimpleAI(self.ai_player)
        self.ai_difficulty = config.AI_DIFFICULTY_SIMPLE
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

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if self.handle_control_click(*event.pos):
                    continue

                row_col = self.pixel_to_cell(*event.pos)
                if row_col is not None:
                    row, col = row_col
                    self.handle_player_move(row, col)

        return True

    def set_mode(self, mode: str) -> None:
        if mode not in config.VALID_MODES:
            return

        self.mode = mode
        self.reset_game()

    def reset_game(self) -> None:
        self.game.reset()
        self.message = ""

    def start_game(self) -> None:
        if self.game.start_timer():
            self.message = ""
        elif self.game.game_over:
            self.message = "Game over"

    def set_difficulty(self, difficulty: str) -> None:
        if difficulty != config.AI_DIFFICULTY_SIMPLE:
            self.message = "Normal and hard AI are coming soon"
            return

        self.ai_difficulty = difficulty
        self.ai = SimpleAI(self.ai_player)
        self.reset_game()

    def undo_move(self) -> None:
        if self.mode == config.MODE_VS_AI:
            if self.game.undo() and self.game.current_player == self.ai_player:
                self.game.undo()
            self.message = ""
            return

        if self.game.undo():
            self.message = ""

    def handle_player_move(self, row: int, col: int) -> None:
        if not self.game.timer_running:
            self.message = "Click Start to begin"
            return

        if self.mode == config.MODE_VS_AI and self.game.current_player == self.ai_player:
            self.message = "AI turn"
            return

        try:
            self.game.make_move(row, col)
            self.message = ""
            self.play_ai_move((row, col))
        except InvalidMoveError as exc:
            self.message = str(exc)
        except GameOverError:
            self.message = "Game over"

    def play_ai_move(self, last_opponent_move: tuple[int, int]) -> None:
        if self.mode != config.MODE_VS_AI:
            return

        if self.game.game_over or self.game.current_player != self.ai_player:
            return

        move = self.ai.choose_move(
            self.game.board,
            last_opponent_move=last_opponent_move,
        )
        if move is None:
            return

        try:
            self.game.make_move(*move)
        except InvalidMoveError as exc:
            self.message = str(exc)
        except GameOverError:
            self.message = "Game over"

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

        if self.game.winning_line:
            points = [self.cell_center(row, col) for row, col in self.game.winning_line]
            pygame.draw.lines(self.screen, config.WIN_COLOR, False, points, 5)
            for center in points:
                pygame.draw.circle(
                    self.screen,
                    config.WIN_COLOR,
                    center,
                    config.STONE_RADIUS + 4,
                    2,
                )

    def draw_status(self) -> None:
        top = config.WINDOW_WIDTH
        pygame.draw.rect(
            self.screen,
            config.BACKGROUND_COLOR,
            (0, top, config.WINDOW_WIDTH, config.INFO_HEIGHT),
        )

        buttons = self.control_buttons()
        self.draw_button(
            buttons["mode_local"],
            "Local 2P",
            selected=self.mode == config.MODE_LOCAL_2P,
        )
        self.draw_button(
            buttons["mode_ai"],
            "VS AI",
            selected=self.mode == config.MODE_VS_AI,
        )
        ai_mode = self.mode == config.MODE_VS_AI
        self.draw_button(
            buttons["difficulty_simple"],
            "Simple",
            selected=ai_mode and self.ai_difficulty == config.AI_DIFFICULTY_SIMPLE,
            disabled=not ai_mode,
        )
        self.draw_button(buttons["difficulty_normal"], "Normal (Soon)", disabled=True)
        self.draw_button(buttons["difficulty_hard"], "Hard (Soon)", disabled=True)
        self.draw_button(
            buttons["start"],
            "Started" if self.game.timer_running else "Start Game",
            disabled=self.game.timer_running or self.game.game_over,
        )
        self.draw_button(buttons["reset"], "Restart")
        self.draw_button(buttons["undo"], "Undo")

        if self.game.winner is not None:
            status = f"{player_label(self.game.winner)} wins"
            color = config.WIN_COLOR
        elif self.game.game_over:
            status = "Draw"
            color = config.WIN_COLOR
        elif not self.game.timer_running:
            status = "Ready: click Start Game"
            color = config.TEXT_COLOR
        else:
            status = f"Turn: {player_label(self.game.current_player)}"
            color = config.TEXT_COLOR

        timer_surface = self.small_font.render(
            "Black "
            f"{self.format_duration(self.game.elapsed_seconds(Player.BLACK))}    "
            "White "
            f"{self.format_duration(self.game.elapsed_seconds(Player.WHITE))}",
            True,
            config.TEXT_COLOR,
        )
        self.screen.blit(timer_surface, (config.MARGIN, top + 114))

        status_surface = self.font.render(status, True, color)
        self.screen.blit(status_surface, (config.MARGIN, top + 136))

        if self.message:
            message_surface = self.small_font.render(
                self.message,
                True,
                config.WIN_COLOR,
            )
            self.screen.blit(message_surface, (config.MARGIN, top + 166))

    def control_buttons(self) -> dict[str, pygame.Rect]:
        top = config.WINDOW_WIDTH
        return {
            "mode_local": pygame.Rect(config.MARGIN, top + 8, 112, 28),
            "mode_ai": pygame.Rect(config.MARGIN + 120, top + 8, 112, 28),
            "difficulty_simple": pygame.Rect(config.MARGIN, top + 42, 96, 28),
            "difficulty_normal": pygame.Rect(config.MARGIN + 104, top + 42, 142, 28),
            "difficulty_hard": pygame.Rect(config.MARGIN + 254, top + 42, 130, 28),
            "start": pygame.Rect(config.MARGIN, top + 76, 128, 28),
            "reset": pygame.Rect(config.MARGIN + 136, top + 76, 104, 28),
            "undo": pygame.Rect(config.MARGIN + 248, top + 76, 88, 28),
        }

    def handle_control_click(self, x: int, y: int) -> bool:
        buttons = self.control_buttons()
        if buttons["mode_local"].collidepoint(x, y):
            self.set_mode(config.MODE_LOCAL_2P)
            return True
        if buttons["mode_ai"].collidepoint(x, y):
            self.set_mode(config.MODE_VS_AI)
            return True
        if buttons["difficulty_simple"].collidepoint(x, y):
            if self.mode == config.MODE_VS_AI:
                self.set_difficulty(config.AI_DIFFICULTY_SIMPLE)
            return True
        if buttons["difficulty_normal"].collidepoint(x, y):
            self.set_difficulty(config.AI_DIFFICULTY_NORMAL)
            return True
        if buttons["difficulty_hard"].collidepoint(x, y):
            self.set_difficulty(config.AI_DIFFICULTY_HARD)
            return True
        if buttons["start"].collidepoint(x, y):
            self.start_game()
            return True
        if buttons["reset"].collidepoint(x, y):
            self.reset_game()
            return True
        if buttons["undo"].collidepoint(x, y):
            self.undo_move()
            return True
        return False

    def draw_button(
        self,
        rect: pygame.Rect,
        label: str,
        *,
        selected: bool = False,
        disabled: bool = False,
    ) -> None:
        if disabled:
            fill_color = (220, 214, 205)
            border_color = (174, 165, 153)
            text_color = (120, 113, 104)
        elif selected:
            fill_color = (47, 111, 103)
            border_color = fill_color
            text_color = config.WHITE_COLOR
        else:
            fill_color = (255, 250, 242)
            border_color = (157, 138, 115)
            text_color = config.TEXT_COLOR

        pygame.draw.rect(self.screen, fill_color, rect, border_radius=5)
        pygame.draw.rect(self.screen, border_color, rect, 1, border_radius=5)
        text_surface = self.small_font.render(label, True, text_color)
        text_rect = text_surface.get_rect(center=rect.center)
        self.screen.blit(text_surface, text_rect)

    def format_duration(self, seconds: float) -> str:
        total_seconds = max(0, int(seconds))
        minutes, remainder = divmod(total_seconds, 60)
        return f"{minutes:02d}:{remainder:02d}"

    def cell_center(self, row: int, col: int) -> tuple[int, int]:
        return (
            config.MARGIN + col * config.CELL_SIZE,
            config.MARGIN + row * config.CELL_SIZE,
        )


def run() -> None:
    PygameGomokuApp().run()
