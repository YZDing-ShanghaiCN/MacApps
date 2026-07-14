from pathlib import Path
import sys
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from gomoku.server.app import app


def token_from(url: str) -> str:
    parsed = urlparse(url)
    assert parsed.query == ""
    return parse_qs(parsed.fragment)["token"][0]


def test_private_room_websocket_syncs_lobby_and_moves() -> None:
    with TestClient(app) as client:
        created = client.post("/api/rooms").json()
        room_id = created["room_id"]
        owner_token = token_from(created["owner_url"])
        guest_token = token_from(created["invite_url"])
        qr_response = client.post(
            "/api/room-invite-qr",
            json={"invite_url": created["invite_url"]},
        )
        assert qr_response.status_code == 200
        assert qr_response.headers["content-type"].startswith("image/svg+xml")
        assert "<svg" in qr_response.text
        room_page = client.get(f"/room/{room_id}")
        assert room_page.status_code == 200
        assert "私人五子棋" in room_page.text

        with client.websocket_connect(f"/ws/rooms/{room_id}") as owner_socket:
            owner_socket.send_json({"type": "authenticate", "token": owner_token})
            owner_waiting = owner_socket.receive_json()["state"]
            assert owner_waiting["phase"] == "waiting_for_guest"
            assert owner_token not in str(owner_waiting)

            with client.websocket_connect(f"/ws/rooms/{room_id}") as guest_socket:
                guest_socket.send_json({"type": "authenticate", "token": guest_token})
                owner_socket.receive_json()
                assert guest_socket.receive_json()["state"]["phase"] == "waiting_for_configuration"

                guest_socket.send_json(
                    {
                        "type": "configure",
                        "color": "white",
                        "first_player": "white",
                    }
                )
                owner_configuration = owner_socket.receive_json()["state"]
                guest_socket.receive_json()
                assert owner_configuration["phase"] == "waiting_for_owner_confirmation"
                assert owner_configuration["configuration"]["first_player"] == 2

                owner_socket.send_json({"type": "accept_configuration"})
                owner_playing = owner_socket.receive_json()["state"]
                guest_playing = guest_socket.receive_json()["state"]
                assert owner_playing["phase"] == "playing"
                assert guest_playing["current_player"] == 2

                guest_socket.send_json({"type": "move", "row": 7, "col": 7})
                owner_after_move = owner_socket.receive_json()["state"]
                guest_socket.receive_json()
                assert owner_after_move["board"][7][7] == 2
                assert owner_after_move["current_player"] == 1
