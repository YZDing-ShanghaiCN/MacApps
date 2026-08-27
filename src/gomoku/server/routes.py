from __future__ import annotations

import re
import random
import threading
import time
from dataclasses import asdict

from fastapi import APIRouter, Body, Header
from fastapi.responses import JSONResponse

from gomoku import config
from gomoku.adapters.web_adapter import serialize_game_state
from gomoku.ai.debug_snapshot import build_debug_snapshot
from gomoku.ai.factory import create_ai
from gomoku.ai.normal_ai import NormalAI
from gomoku.ai.simple_ai import SimpleAI
from gomoku.core.board import Board
from gomoku.core.enums import Player
from gomoku.core.exceptions import GameOverError, InvalidMoveError
from gomoku.core.game import GomokuGame


router = APIRouter(prefix="/api")
AI_PLAYER = Player.WHITE  # Backward-compatible default; sessions own the value.
SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,80}$")


class LocalGameSession:
    def __init__(self) -> None:
        self.game = GomokuGame()
        self.current_mode = config.DEFAULT_MODE
        self.current_ai_difficulty = config.DEFAULT_AI_DIFFICULTY
        self.human_color_choice = config.DEFAULT_HUMAN_COLOR
        self._color_rng = random.Random()
        self.ai_player = Player.WHITE
        self.ai = create_ai(self.current_ai_difficulty, self.ai_player)
        self.ai_thinking = False
        self.ai_generation = 0
        self.ai_error: str | None = None
        self.ai_cancel_event: threading.Event | None = None
        self.last_accessed = time.monotonic()
        self.lock = threading.RLock()


default_session = LocalGameSession()
game = default_session.game  # Backward-compatible test and adapter alias.
state_lock = default_session.lock
_sessions: dict[str, LocalGameSession] = {"default": default_session}
_sessions_lock = threading.Lock()


def get_session(session_id: object = None) -> LocalGameSession:
    key = session_id if isinstance(session_id, str) else "default"
    if key != "default" and SESSION_ID_PATTERN.fullmatch(key) is None:
        key = "default"
    with _sessions_lock:
        session = _sessions.get(key)
        if session is None:
            _cleanup_local_sessions_locked()
            session = LocalGameSession()
            _sessions[key] = session
        session.last_accessed = time.monotonic()
        return session


def _cleanup_local_sessions_locked() -> None:
    now = time.monotonic()
    expired = [
        key
        for key, session in _sessions.items()
        if key != "default"
        and not session.ai_thinking
        and now - session.last_accessed > config.LOCAL_GAME_SESSION_TTL_SECONDS
    ]
    for key in expired:
        del _sessions[key]
    if len(_sessions) < config.MAX_LOCAL_GAME_SESSIONS:
        return
    oldest = sorted(
        (
            (session.last_accessed, key)
            for key, session in _sessions.items()
            if key != "default" and not session.ai_thinking
        )
    )
    for _last_accessed, key in oldest[
        : max(1, len(_sessions) - config.MAX_LOCAL_GAME_SESSIONS + 1)
    ]:
        del _sessions[key]


def active_ai_player(session: LocalGameSession | None = None) -> Player | None:
    session = default_session if session is None else session
    if session.current_mode == config.MODE_VS_AI:
        return session.ai_player
    return None


def active_human_player(session: LocalGameSession | None = None) -> Player | None:
    session = default_session if session is None else session
    ai_player = active_ai_player(session)
    return ai_player.opponent if ai_player is not None else None


def state_response(session: LocalGameSession | None = None) -> dict:
    session = default_session if session is None else session
    state = serialize_game_state(
        session.game,
        mode=session.current_mode,
        ai_player=active_ai_player(session),
        ai_difficulty=session.current_ai_difficulty,
        ai_thinking=session.ai_thinking,
        ai_error=session.ai_error,
        human_player=active_human_player(session),
        human_color_choice=session.human_color_choice,
    )
    if isinstance(session.ai, NormalAI):
        state["ai_search_stats"] = asdict(session.ai.last_search_stats)
    else:
        state["ai_search_stats"] = None
    if isinstance(session.ai, SimpleAI):
        state["ai_decision"] = asdict(session.ai.last_decision)
    elif isinstance(session.ai, NormalAI):
        stats = session.ai.last_search_stats
        state["ai_decision"] = {
            "reason": stats.decision_reason,
            "selected_move": stats.selected_move,
            "candidates": [
                {"move": item.move, "score": item.score}
                for item in stats.root_moves[:3]
            ],
        }
    else:
        state["ai_decision"] = None
    return state


def debug_position_response(session: LocalGameSession | None = None) -> dict:
    """Serialize a reproducible local-game snapshot for issue reports."""

    session = default_session if session is None else session
    return build_debug_snapshot(
        session.game,
        mode=session.current_mode,
        ai_player=active_ai_player(session),
        ai_difficulty=session.current_ai_difficulty,
        ai=session.ai,
    )


def validate_mode(mode: object) -> str | None:
    if isinstance(mode, str) and mode in config.VALID_MODES:
        return mode
    return None


def validate_difficulty(difficulty: object) -> str | None:
    if (
        isinstance(difficulty, str)
        and difficulty in config.AVAILABLE_AI_DIFFICULTIES
    ):
        return difficulty
    return None


def validate_human_color(color: object) -> str | None:
    if isinstance(color, str) and color in config.HUMAN_COLOR_CHOICES:
        return color
    return None


def invalid_mode_response() -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"error": f"Mode must be one of: {', '.join(config.VALID_MODES)}."},
    )


def invalid_difficulty_response() -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={
            "error": (
                "AI difficulty must be one of: "
                f"{', '.join(config.AVAILABLE_AI_DIFFICULTIES)}."
            )
        },
    )


def invalid_human_color_response() -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={
            "error": (
                "Human color must be one of: "
                f"{', '.join(config.HUMAN_COLOR_CHOICES)}."
            )
        },
    )


def ai_busy_response() -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={"error": "AI is currently thinking."},
    )


def set_current_mode(
    mode: str,
    session: LocalGameSession | None = None,
) -> None:
    session = default_session if session is None else session
    session.current_mode = mode


def set_current_difficulty(
    difficulty: str,
    session: LocalGameSession | None = None,
) -> None:
    session = default_session if session is None else session
    if difficulty not in config.AVAILABLE_AI_DIFFICULTIES:
        raise ValueError(f"AI difficulty is not available: {difficulty}.")
    session.current_ai_difficulty = difficulty
    session.ai = create_ai(difficulty, session.ai_player)


def set_human_color(
    color: str,
    session: LocalGameSession | None = None,
) -> None:
    session = default_session if session is None else session
    if color not in config.HUMAN_COLOR_CHOICES:
        raise ValueError(f"Human color is not available: {color}.")
    session.human_color_choice = color
    _resolve_players(session)
    session.ai = create_ai(session.current_ai_difficulty, session.ai_player)


def _resolve_players(session: LocalGameSession) -> None:
    if session.human_color_choice == config.HUMAN_COLOR_BLACK:
        session.ai_player = Player.WHITE
    elif session.human_color_choice == config.HUMAN_COLOR_WHITE:
        session.ai_player = Player.BLACK
    else:
        session.ai_player = session._color_rng.choice(
            (Player.BLACK, Player.WHITE)
        )


def reset_local_game(
    session: LocalGameSession,
    *,
    reroll_random_color: bool = True,
) -> None:
    if reroll_random_color and (
        session.human_color_choice == config.HUMAN_COLOR_RANDOM
    ):
        _resolve_players(session)
    session.ai = create_ai(session.current_ai_difficulty, session.ai_player)
    session.game.reset()


def maybe_play_ai_move(
    last_opponent_move: tuple[int, int] | None,
    session: LocalGameSession | None = None,
) -> None:
    session = default_session if session is None else session
    if (
        session.current_mode != config.MODE_VS_AI
        or session.game.game_over
        or session.game.current_player != session.ai_player
    ):
        return

    snapshot = Board(session.game.board.size)
    snapshot.grid = session.game.board.to_list()
    session.ai_generation += 1
    generation = session.ai_generation
    session.ai_thinking = True
    selected_ai = session.ai
    cancel_event = threading.Event()
    session.ai_cancel_event = cancel_event
    threading.Thread(
        target=_run_ai_worker,
        args=(
            session,
            generation,
            selected_ai,
            snapshot,
            last_opponent_move,
            cancel_event,
        ),
        daemon=True,
    ).start()


def _run_ai_worker(
    session: LocalGameSession,
    generation: int,
    selected_ai,
    snapshot: Board,
    last_opponent_move: tuple[int, int] | None,
    cancel_event: threading.Event,
) -> None:
    try:
        if isinstance(selected_ai, NormalAI):
            ai_move = selected_ai.choose_move(
                snapshot,
                last_opponent_move=last_opponent_move,
                cancel_event=cancel_event,
            )
        else:
            ai_move = selected_ai.choose_move(
                snapshot,
                last_opponent_move=last_opponent_move,
            )
        error = None
    except Exception as exc:  # Keep the web game recoverable after AI errors.
        ai_move = None
        error = str(exc)

    with session.lock:
        if generation != session.ai_generation:
            return
        session.ai_error = error
        if (
            ai_move is not None
            and session.current_mode == config.MODE_VS_AI
            and not session.game.game_over
            and session.game.current_player == session.ai_player
            and session.game.board.is_empty(*ai_move)
        ):
            session.game.make_move(*ai_move)
        session.ai_thinking = False
        session.ai_cancel_event = None


def cancel_pending_ai(session: LocalGameSession | None = None) -> None:
    session = default_session if session is None else session
    session.ai_generation += 1
    if session.ai_cancel_event is not None:
        session.ai_cancel_event.set()
        session.ai_cancel_event = None
    session.ai_thinking = False
    session.ai_error = None


def undo_for_current_mode(session: LocalGameSession | None = None) -> None:
    session = default_session if session is None else session
    if session.current_mode == config.MODE_VS_AI:
        if (
            len(session.game.move_history) == 1
            and session.game.move_history[-1][2] == session.ai_player
        ):
            return
        if session.game.undo() and session.game.current_player == session.ai_player:
            session.game.undo()
        return
    session.game.undo()


@router.get("/state")
def get_state(x_gomoku_session: str | None = Header(default=None)) -> dict:
    session = get_session(x_gomoku_session)
    with session.lock:
        return state_response(session)


@router.get("/debug-position")
def get_debug_position(
    x_gomoku_session: str | None = Header(default=None),
) -> dict:
    session = get_session(x_gomoku_session)
    with session.lock:
        return debug_position_response(session)


@router.post("/move")
def make_move(
    payload: dict = Body(...),
    x_gomoku_session: str | None = Header(default=None),
):
    session = get_session(x_gomoku_session)
    try:
        row = int(payload["row"])
        col = int(payload["col"])
    except (KeyError, TypeError, ValueError):
        return JSONResponse(
            status_code=400,
            content={"error": "Move request must include integer row and col."},
        )

    with session.lock:
        if session.ai_thinking or (
            session.current_mode == config.MODE_VS_AI
            and session.game.current_player == session.ai_player
        ):
            return ai_busy_response()
        try:
            session.game.make_move(row, col)
        except InvalidMoveError as exc:
            return JSONResponse(status_code=400, content={"error": str(exc)})
        except GameOverError as exc:
            return JSONResponse(status_code=400, content={"error": str(exc)})
        if (
            session.current_mode == config.MODE_VS_AI
            and not session.game.game_over
            and session.game.current_player == session.ai_player
        ):
            maybe_play_ai_move((row, col), session)
        return state_response(session)


@router.post("/reset")
def reset_game(
    payload: dict | None = Body(default=None),
    x_gomoku_session: str | None = Header(default=None),
):
    session = get_session(x_gomoku_session)
    with session.lock:
        cancel_pending_ai(session)
        color_changed = False
        if payload is not None:
            if not isinstance(payload, dict):
                return JSONResponse(
                    status_code=400,
                    content={"error": "Reset request body must be an object."},
                )
            if "mode" in payload:
                requested_mode = validate_mode(payload["mode"])
                if requested_mode is None:
                    return invalid_mode_response()
                set_current_mode(requested_mode, session)
            if "ai_difficulty" in payload:
                difficulty = validate_difficulty(payload["ai_difficulty"])
                if difficulty is None:
                    return invalid_difficulty_response()
                set_current_difficulty(difficulty, session)
            if "human_color" in payload:
                color = validate_human_color(payload["human_color"])
                if color is None:
                    return invalid_human_color_response()
                set_human_color(color, session)
                color_changed = True
        reset_local_game(session, reroll_random_color=not color_changed)
        return state_response(session)


@router.post("/start")
def start_game(x_gomoku_session: str | None = Header(default=None)):
    session = get_session(x_gomoku_session)
    with session.lock:
        if session.ai_thinking:
            return ai_busy_response()
        session.game.start_timer()
        if (
            session.current_mode == config.MODE_VS_AI
            and session.game.current_player == session.ai_player
        ):
            maybe_play_ai_move(None, session)
        return state_response(session)


@router.post("/undo")
def undo_move(x_gomoku_session: str | None = Header(default=None)) -> dict:
    session = get_session(x_gomoku_session)
    with session.lock:
        cancel_pending_ai(session)
        undo_for_current_mode(session)
        return state_response(session)


@router.post("/mode")
def change_mode(
    payload: dict = Body(...),
    x_gomoku_session: str | None = Header(default=None),
):
    session = get_session(x_gomoku_session)
    try:
        requested_mode = validate_mode(payload["mode"])
    except (KeyError, TypeError):
        requested_mode = None
    if requested_mode is None:
        return invalid_mode_response()
    with session.lock:
        cancel_pending_ai(session)
        set_current_mode(requested_mode, session)
        reset_local_game(session)
        return state_response(session)


@router.post("/difficulty")
def change_difficulty(
    payload: dict = Body(...),
    x_gomoku_session: str | None = Header(default=None),
):
    session = get_session(x_gomoku_session)
    try:
        difficulty = validate_difficulty(payload["difficulty"])
    except (KeyError, TypeError):
        difficulty = None
    if difficulty is None:
        return invalid_difficulty_response()
    with session.lock:
        cancel_pending_ai(session)
        set_current_difficulty(difficulty, session)
        reset_local_game(session)
        return state_response(session)


@router.post("/ai-color")
def change_ai_color(
    payload: dict = Body(...),
    x_gomoku_session: str | None = Header(default=None),
):
    session = get_session(x_gomoku_session)
    try:
        color = validate_human_color(payload["human_color"])
    except (KeyError, TypeError):
        color = None
    if color is None:
        return invalid_human_color_response()
    with session.lock:
        cancel_pending_ai(session)
        set_human_color(color, session)
        reset_local_game(session, reroll_random_color=False)
        return state_response(session)
