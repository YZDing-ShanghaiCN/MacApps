from __future__ import annotations

import asyncio
from pathlib import Path
import sys

import pytest


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from gomoku.core.enums import Player
from gomoku.server.rooms import (
    RoomAccessError,
    RoomManager,
    RoomPhase,
    RoomRole,
)


def test_private_room_requires_a_valid_seat_token() -> None:
    async def scenario() -> None:
        manager = RoomManager()
        created = await manager.create()

        room, role = await manager.authorize(created.room_id, created.owner_token)
        assert room.room_id == created.room_id
        assert role == RoomRole.OWNER

        with pytest.raises(RoomAccessError):
            await manager.authorize(created.room_id, "not-the-room-token")

    asyncio.run(scenario())


def test_guest_chooses_color_and_first_player_before_owner_starts() -> None:
    async def scenario() -> None:
        manager = RoomManager()
        created = await manager.create()
        room, owner_role = await manager.authorize(created.room_id, created.owner_token)
        _room, guest_role = await manager.authorize(created.room_id, created.guest_token)
        room.phase = RoomPhase.WAITING_FOR_CONFIGURATION

        error = await manager.perform(
            room,
            guest_role,
            {
                "type": "configure",
                "color": "white",
                "first_player": "white",
            },
        )

        assert error is None
        assert room.phase == RoomPhase.WAITING_FOR_OWNER_CONFIRMATION
        assert room.player_for_role(guest_role) == Player.WHITE
        assert room.player_for_role(owner_role) == Player.BLACK
        assert room.first_player == Player.WHITE

        error = await manager.perform(
            room,
            owner_role,
            {"type": "accept_configuration"},
        )

        assert error is None
        assert room.phase == RoomPhase.PLAYING
        assert room.game.current_player == Player.WHITE
        assert room.game.timer_running is True

    asyncio.run(scenario())


def test_only_the_assigned_player_can_move_on_their_turn() -> None:
    async def scenario() -> None:
        manager = RoomManager()
        created = await manager.create()
        room, owner_role = await manager.authorize(created.room_id, created.owner_token)
        _room, guest_role = await manager.authorize(created.room_id, created.guest_token)
        room.phase = RoomPhase.WAITING_FOR_CONFIGURATION
        await manager.perform(
            room,
            guest_role,
            {
                "type": "configure",
                "color": "white",
                "first_player": "white",
            },
        )
        await manager.perform(room, owner_role, {"type": "accept_configuration"})

        error = await manager.perform(
            room,
            owner_role,
            {"type": "move", "row": 7, "col": 7},
        )
        assert error == "还没有轮到你落子。"

        assert await manager.perform(
            room,
            guest_role,
            {"type": "move", "row": 7, "col": 7},
        ) is None
        assert room.game.current_player == Player.BLACK

        assert await manager.perform(
            room,
            owner_role,
            {"type": "move", "row": 7, "col": 8},
        ) is None
        assert len(room.game.move_history) == 2

    asyncio.run(scenario())


def test_guest_cannot_start_or_configure_from_the_owner_seat() -> None:
    async def scenario() -> None:
        manager = RoomManager()
        created = await manager.create()
        room, owner_role = await manager.authorize(created.room_id, created.owner_token)
        _room, guest_role = await manager.authorize(created.room_id, created.guest_token)
        room.phase = RoomPhase.WAITING_FOR_CONFIGURATION

        assert await manager.perform(
            room,
            owner_role,
            {
                "type": "configure",
                "color": "black",
                "first_player": "black",
            },
        ) == "只有受邀者可以选择棋色和先手。"
        assert await manager.perform(
            room,
            guest_role,
            {"type": "accept_configuration"},
        ) == "只有房主可以确认并开始对局。"

    asyncio.run(scenario())


def test_undo_and_rematch_require_the_other_players_confirmation() -> None:
    async def scenario() -> None:
        manager = RoomManager()
        created = await manager.create()
        room, owner_role = await manager.authorize(created.room_id, created.owner_token)
        _room, guest_role = await manager.authorize(created.room_id, created.guest_token)
        room.phase = RoomPhase.WAITING_FOR_CONFIGURATION
        await manager.perform(
            room,
            guest_role,
            {
                "type": "configure",
                "color": "white",
                "first_player": "white",
            },
        )
        await manager.perform(room, owner_role, {"type": "accept_configuration"})

        await manager.perform(
            room,
            guest_role,
            {"type": "move", "row": 0, "col": 0},
        )
        await manager.perform(
            room,
            owner_role,
            {"type": "move", "row": 1, "col": 0},
        )
        assert await manager.perform(room, owner_role, {"type": "request_undo"}) is None
        assert room.undo_requested_by == owner_role
        assert await manager.perform(room, guest_role, {"type": "accept_undo"}) is None
        assert len(room.game.move_history) == 1

        winning_moves = [
            (owner_role, 1, 1),
            (guest_role, 0, 1),
            (owner_role, 1, 2),
            (guest_role, 0, 2),
            (owner_role, 1, 3),
            (guest_role, 0, 3),
            (owner_role, 1, 4),
            (guest_role, 0, 4),
        ]
        for role, row, col in winning_moves:
            assert await manager.perform(
                room,
                role,
                {"type": "move", "row": row, "col": col},
            ) is None

        assert room.phase == RoomPhase.FINISHED
        assert await manager.perform(room, guest_role, {"type": "request_rematch"}) is None
        assert await manager.perform(room, owner_role, {"type": "accept_rematch"}) is None
        assert room.phase == RoomPhase.PLAYING
        assert room.game.current_player == Player.WHITE

    asyncio.run(scenario())
