from __future__ import annotations

import asyncio
import hashlib
import secrets
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import parse_qs, urlparse

import qrcode
from fastapi import APIRouter, Body, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response
from qrcode.image.svg import SvgPathImage

from gomoku import config
from gomoku.core.enums import Player
from gomoku.core.exceptions import GameOverError, InvalidMoveError
from gomoku.core.game import GomokuGame


router = APIRouter()


class RoomRole(str, Enum):
    OWNER = "owner"
    GUEST = "guest"


class RoomPhase(str, Enum):
    WAITING_FOR_GUEST = "waiting_for_guest"
    WAITING_FOR_CONFIGURATION = "waiting_for_configuration"
    WAITING_FOR_OWNER_CONFIRMATION = "waiting_for_owner_confirmation"
    PLAYING = "playing"
    FINISHED = "finished"


class RoomAccessError(Exception):
    """Raised when a room id or private seat token is invalid."""


class RoomActionError(Exception):
    """Raised when a room action is invalid for its current state."""


class RoomRateLimitError(Exception):
    """Raised when one client creates rooms too frequently."""


class RoomCapacityError(Exception):
    """Raised when the in-memory room limit is reached."""


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _player_from_choice(value: object) -> Player:
    if value == "black":
        return Player.BLACK
    if value == "white":
        return Player.WHITE
    raise RoomActionError("棋色和先手必须选择黑棋或白棋。")


@dataclass(frozen=True)
class CreatedRoom:
    room_id: str
    owner_token: str
    guest_token: str


@dataclass
class GameRoom:
    room_id: str
    owner_token_hash: str
    guest_token_hash: str
    game: GomokuGame = field(default_factory=GomokuGame)
    phase: RoomPhase = RoomPhase.WAITING_FOR_GUEST
    guest_player: Player | None = None
    first_player: Player | None = None
    undo_requested_by: RoomRole | None = None
    rematch_requested_by: RoomRole | None = None
    connections: dict[RoomRole, WebSocket | None] = field(
        default_factory=lambda: {
            RoomRole.OWNER: None,
            RoomRole.GUEST: None,
        }
    )
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_activity: float = field(default_factory=time.monotonic)
    paused_for_disconnect: bool = False

    @property
    def owner_player(self) -> Player | None:
        if self.guest_player is None:
            return None
        return self.guest_player.opponent

    def role_for_token(self, token: str) -> RoomRole | None:
        token_hash = _token_hash(token)
        if secrets.compare_digest(token_hash, self.owner_token_hash):
            return RoomRole.OWNER
        if secrets.compare_digest(token_hash, self.guest_token_hash):
            return RoomRole.GUEST
        return None

    def player_for_role(self, role: RoomRole) -> Player | None:
        if role == RoomRole.GUEST:
            return self.guest_player
        return self.owner_player

    def state_for(self, role: RoomRole) -> dict:
        configuration = None
        if self.guest_player is not None and self.first_player is not None:
            configuration = {
                "guest_player": int(self.guest_player),
                "owner_player": int(self.owner_player),
                "first_player": int(self.first_player),
            }

        return {
            "room_id": self.room_id,
            "phase": self.phase.value,
            "you": {
                "role": role.value,
                "player": (
                    int(self.player_for_role(role))
                    if self.player_for_role(role) is not None
                    else None
                ),
            },
            "participants": {
                "owner_connected": bool(self.connections[RoomRole.OWNER]),
                "guest_connected": bool(self.connections[RoomRole.GUEST]),
            },
            "paused_for_disconnect": self.paused_for_disconnect,
            "configuration": configuration,
            "undo_requested_by": (
                self.undo_requested_by.value
                if self.undo_requested_by is not None
                else None
            ),
            "rematch_requested_by": (
                self.rematch_requested_by.value
                if self.rematch_requested_by is not None
                else None
            ),
            **self.game.get_state(),
        }


class RoomManager:
    """In-memory private rooms for two-player browser games."""

    def __init__(
        self,
        room_ttl_seconds: int = config.ROOM_TTL_SECONDS,
        room_create_limit: int = config.ROOM_CREATE_LIMIT,
        room_create_window_seconds: int = config.ROOM_CREATE_WINDOW_SECONDS,
        max_active_rooms: int = config.MAX_ACTIVE_ROOMS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._rooms: dict[str, GameRoom] = {}
        self._lock = asyncio.Lock()
        self._room_ttl_seconds = room_ttl_seconds
        self._room_create_limit = room_create_limit
        self._room_create_window_seconds = room_create_window_seconds
        self._max_active_rooms = max_active_rooms
        self._clock = clock
        self._room_creation_times: dict[str, deque[float]] = {}

    async def create(self, client_key: str = "anonymous") -> CreatedRoom:
        async with self._lock:
            now = self._clock()
            self._remove_expired_rooms(now)
            self._remove_expired_creation_records(now)
            self._check_creation_limit(client_key, now)
            if len(self._rooms) >= self._max_active_rooms:
                raise RoomCapacityError("当前房间数量已达上限，请稍后再试。")
            room_id = self._new_room_id()
            owner_token = secrets.token_urlsafe(32)
            guest_token = secrets.token_urlsafe(32)
            room = GameRoom(
                room_id=room_id,
                owner_token_hash=_token_hash(owner_token),
                guest_token_hash=_token_hash(guest_token),
            )
            room.last_activity = now
            self._rooms[room_id] = room
            return CreatedRoom(room_id, owner_token, guest_token)

    async def cleanup_expired_rooms(self) -> None:
        async with self._lock:
            self._remove_expired_rooms(self._clock())

    async def authorize(self, room_id: str, token: object) -> tuple[GameRoom, RoomRole]:
        if not isinstance(token, str) or not token:
            raise RoomAccessError("Invalid room link.")

        async with self._lock:
            room = self._rooms.get(room_id)
        if room is None:
            raise RoomAccessError("Invalid room link.")

        role = room.role_for_token(token)
        if role is None:
            raise RoomAccessError("Invalid room link.")
        return room, role

    async def connect(
        self,
        websocket: WebSocket,
        room_id: str,
        token: object,
    ) -> tuple[GameRoom, RoomRole, WebSocket | None]:
        room, role = await self.authorize(room_id, token)
        async with room.lock:
            replaced_connection = room.connections[role]
            room.connections[role] = websocket
            if role == RoomRole.GUEST and room.phase == RoomPhase.WAITING_FOR_GUEST:
                room.phase = RoomPhase.WAITING_FOR_CONFIGURATION
            if room.paused_for_disconnect and self._both_players_connected(room):
                room.game.start_timer()
                room.paused_for_disconnect = False
            room.last_activity = self._clock()
            await self._broadcast_locked(room)
        return room, role, replaced_connection

    async def disconnect(
        self,
        room: GameRoom,
        role: RoomRole,
        websocket: WebSocket,
    ) -> None:
        async with room.lock:
            if room.connections[role] is not websocket:
                return
            room.connections[role] = None
            if room.phase == RoomPhase.PLAYING and not self._both_players_connected(room):
                room.game.pause_timer()
                room.paused_for_disconnect = True
            room.last_activity = self._clock()
            await self._broadcast_locked(room)

    async def perform(
        self,
        room: GameRoom,
        role: RoomRole,
        message: object,
    ) -> str | None:
        if not isinstance(message, dict):
            return "请求格式无效。"

        action = message.get("type")
        if not isinstance(action, str):
            return "请求格式无效。"

        try:
            async with room.lock:
                self._perform_locked(room, role, action, message)
                room.last_activity = self._clock()
                await self._broadcast_locked(room)
        except RoomActionError as exc:
            return str(exc)
        return None

    async def send_error(self, websocket: WebSocket, message: str) -> None:
        try:
            await websocket.send_json({"type": "error", "error": message})
        except (RuntimeError, WebSocketDisconnect):
            return

    def _perform_locked(
        self,
        room: GameRoom,
        role: RoomRole,
        action: str,
        message: dict,
    ) -> None:
        if action == "configure":
            self._configure_room(room, role, message)
            return
        if action == "accept_configuration":
            self._accept_configuration(room, role)
            return
        if action == "move":
            self._make_move(room, role, message)
            return
        if action == "request_undo":
            self._request_undo(room, role)
            return
        if action == "accept_undo":
            self._accept_undo(room, role)
            return
        if action == "request_rematch":
            self._request_rematch(room, role)
            return
        if action == "accept_rematch":
            self._accept_rematch(room, role)
            return
        raise RoomActionError("不支持此操作。")

    def _configure_room(
        self,
        room: GameRoom,
        role: RoomRole,
        message: dict,
    ) -> None:
        if role != RoomRole.GUEST:
            raise RoomActionError("只有受邀者可以选择棋色和先手。")
        if room.phase not in {
            RoomPhase.WAITING_FOR_CONFIGURATION,
            RoomPhase.WAITING_FOR_OWNER_CONFIRMATION,
        }:
            raise RoomActionError("当前不能修改对局设置。")

        guest_player = _player_from_choice(message.get("color"))
        first_player = _player_from_choice(message.get("first_player"))
        room.guest_player = guest_player
        room.first_player = first_player
        room.undo_requested_by = None
        room.rematch_requested_by = None
        room.phase = RoomPhase.WAITING_FOR_OWNER_CONFIRMATION

    def _accept_configuration(self, room: GameRoom, role: RoomRole) -> None:
        if role != RoomRole.OWNER:
            raise RoomActionError("只有房主可以确认并开始对局。")
        if (
            room.phase != RoomPhase.WAITING_FOR_OWNER_CONFIRMATION
            or room.first_player is None
        ):
            raise RoomActionError("请先等待受邀者完成设置。")
        if not self._both_players_connected(room):
            raise RoomActionError("请等待双方在线后再开始对局。")

        room.game.reset(starting_player=room.first_player)
        room.game.start_timer()
        room.phase = RoomPhase.PLAYING
        room.paused_for_disconnect = False

    def _make_move(self, room: GameRoom, role: RoomRole, message: dict) -> None:
        if room.phase != RoomPhase.PLAYING:
            raise RoomActionError("对局尚未开始。")
        if room.paused_for_disconnect:
            raise RoomActionError("对方暂时断线，对局已暂停。")

        player = room.player_for_role(role)
        if player is None or room.game.current_player != player:
            raise RoomActionError("还没有轮到你落子。")

        row = message.get("row")
        col = message.get("col")
        if isinstance(row, bool) or isinstance(col, bool):
            raise RoomActionError("落子位置无效。")
        if not isinstance(row, int) or not isinstance(col, int):
            raise RoomActionError("落子位置无效。")

        try:
            room.game.make_move(row, col)
        except (InvalidMoveError, GameOverError) as exc:
            raise RoomActionError(str(exc)) from exc

        room.undo_requested_by = None
        if room.game.game_over:
            room.phase = RoomPhase.FINISHED

    def _request_undo(self, room: GameRoom, role: RoomRole) -> None:
        if room.phase != RoomPhase.PLAYING or not room.game.move_history:
            raise RoomActionError("当前不能请求悔棋。")
        if room.paused_for_disconnect:
            raise RoomActionError("对方暂时断线，对局已暂停。")
        if room.undo_requested_by is not None:
            raise RoomActionError("已有待确认的悔棋请求。")
        room.undo_requested_by = role

    def _accept_undo(self, room: GameRoom, role: RoomRole) -> None:
        if room.undo_requested_by is None or room.undo_requested_by == role:
            raise RoomActionError("没有可确认的悔棋请求。")
        if room.paused_for_disconnect:
            raise RoomActionError("对方暂时断线，对局已暂停。")
        if not room.game.undo():
            raise RoomActionError("当前不能悔棋。")
        room.undo_requested_by = None

    def _request_rematch(self, room: GameRoom, role: RoomRole) -> None:
        if room.phase != RoomPhase.FINISHED:
            raise RoomActionError("对局结束后才能请求再来一局。")
        if room.rematch_requested_by is not None:
            raise RoomActionError("已有待确认的再来一局请求。")
        room.rematch_requested_by = role

    def _accept_rematch(self, room: GameRoom, role: RoomRole) -> None:
        if room.rematch_requested_by is None or room.rematch_requested_by == role:
            raise RoomActionError("没有可确认的再来一局请求。")
        if room.first_player is None:
            raise RoomActionError("对局设置无效。")
        if not self._both_players_connected(room):
            raise RoomActionError("请等待双方重新连接后再开始。")

        room.game.reset(starting_player=room.first_player)
        room.game.start_timer()
        room.phase = RoomPhase.PLAYING
        room.undo_requested_by = None
        room.rematch_requested_by = None
        room.paused_for_disconnect = False

    async def _broadcast_locked(self, room: GameRoom) -> None:
        for role, websocket in room.connections.items():
            if websocket is None:
                continue
            payload = {"type": "state", "state": room.state_for(role)}
            try:
                await websocket.send_json(payload)
            except (RuntimeError, WebSocketDisconnect):
                if room.connections[role] is websocket:
                    room.connections[role] = None
                    if room.phase == RoomPhase.PLAYING and not self._both_players_connected(room):
                        room.game.pause_timer()
                        room.paused_for_disconnect = True

    def _new_room_id(self) -> str:
        room_id = secrets.token_urlsafe(9)
        while room_id in self._rooms:
            room_id = secrets.token_urlsafe(9)
        return room_id

    def _both_players_connected(self, room: GameRoom) -> bool:
        return all(room.connections.values())

    def _check_creation_limit(self, client_key: str, now: float) -> None:
        recent_creations = self._room_creation_times.setdefault(client_key, deque())
        if len(recent_creations) >= self._room_create_limit:
            raise RoomRateLimitError("创建房间过于频繁，请稍后再试。")
        recent_creations.append(now)

    def _remove_expired_creation_records(self, now: float) -> None:
        expiration = now - self._room_create_window_seconds
        for client_key, recent_creations in tuple(self._room_creation_times.items()):
            while recent_creations and recent_creations[0] <= expiration:
                recent_creations.popleft()
            if not recent_creations:
                del self._room_creation_times[client_key]

    def _remove_expired_rooms(self, now: float) -> None:
        expiration = now - self._room_ttl_seconds
        expired_ids = [
            room_id
            for room_id, room in self._rooms.items()
            if not any(room.connections.values()) and room.last_activity < expiration
        ]
        for room_id in expired_ids:
            del self._rooms[room_id]


room_manager = RoomManager()


def _client_key(request: Request) -> str:
    for header_name in ("cf-connecting-ip", "x-forwarded-for"):
        value = request.headers.get(header_name)
        if value:
            return value.split(",", maxsplit=1)[0].strip()
    return request.client.host if request.client is not None else "unknown"


def _invite_link_credentials(invite_url: object) -> tuple[str, str] | None:
    if not isinstance(invite_url, str) or len(invite_url) > 1024:
        return None

    parsed = urlparse(invite_url)
    path_segments = [segment for segment in parsed.path.split("/") if segment]
    token = parse_qs(parsed.fragment).get("token", [None])[0]
    if len(path_segments) != 2 or path_segments[0] != "room" or not token:
        return None
    return path_segments[1], token


def _is_loopback_url(url: str) -> bool:
    hostname = urlparse(url).hostname
    return hostname in {"127.0.0.1", "localhost", "::1"}


@router.post("/api/rooms", status_code=201)
async def create_room(request: Request) -> dict:
    request_base_url = str(request.base_url).rstrip("/")
    if not config.PUBLIC_BASE_URL and _is_loopback_url(request_base_url):
        return JSONResponse(
            status_code=400,
            content={
                "error": (
                    "当前是本机地址，不能创建跨网房间。请使用 "
                    "python gomoku/scripts/run_quick_tunnel.py 启动公网对战服务。"
                )
            },
        )

    try:
        created = await room_manager.create(_client_key(request))
    except RoomRateLimitError as exc:
        return JSONResponse(status_code=429, content={"error": str(exc)})
    except RoomCapacityError as exc:
        return JSONResponse(status_code=503, content={"error": str(exc)})
    base_url = config.PUBLIC_BASE_URL or request_base_url
    owner_url = f"{base_url}/room/{created.room_id}#token={created.owner_token}"
    invite_url = f"{base_url}/room/{created.room_id}#token={created.guest_token}"
    return {
        "room_id": created.room_id,
        "owner_url": owner_url,
        "invite_url": invite_url,
    }


@router.post("/api/room-invite-qr")
async def room_invite_qr(payload: dict = Body(...)) -> Response:
    credentials = _invite_link_credentials(payload.get("invite_url"))
    if credentials is None:
        return JSONResponse(status_code=400, content={"error": "邀请链接无效。"})

    room_id, token = credentials
    try:
        await room_manager.authorize(room_id, token)
    except RoomAccessError:
        return JSONResponse(status_code=404, content={"error": "邀请链接无效或已失效。"})

    image = qrcode.make(payload["invite_url"], image_factory=SvgPathImage)
    return Response(
        content=image.to_string(encoding="unicode"),
        media_type="image/svg+xml",
        headers={"Cache-Control": "no-store"},
    )


@router.websocket("/ws/rooms/{room_id}")
async def room_websocket(websocket: WebSocket, room_id: str) -> None:
    await websocket.accept()
    try:
        authentication = await asyncio.wait_for(
            websocket.receive_json(),
            timeout=config.ROOM_AUTH_TIMEOUT_SECONDS,
        )
    except (asyncio.TimeoutError, ValueError, WebSocketDisconnect):
        await websocket.close(code=1008)
        return

    if (
        not isinstance(authentication, dict)
        or authentication.get("type") != "authenticate"
    ):
        await websocket.close(code=1008)
        return

    try:
        room, role, replaced_connection = await room_manager.connect(
            websocket,
            room_id,
            authentication.get("token"),
        )
    except RoomAccessError:
        await websocket.close(code=1008)
        return

    if replaced_connection is not None:
        try:
            await replaced_connection.close(code=4001)
        except (RuntimeError, WebSocketDisconnect):
            pass

    try:
        while True:
            try:
                message = await websocket.receive_json()
            except ValueError:
                await room_manager.send_error(websocket, "请求格式无效。")
                continue
            error = await room_manager.perform(room, role, message)
            if error is not None:
                await room_manager.send_error(websocket, error)
    except WebSocketDisconnect:
        await room_manager.disconnect(room, role, websocket)
