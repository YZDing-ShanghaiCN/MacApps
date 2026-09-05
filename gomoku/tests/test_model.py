from pathlib import Path
import sys


SRC_DIR = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SRC_DIR))

pytest = sys.modules.get("pytest")
if pytest is None:
    import pytest

torch = pytest.importorskip("torch")

import numpy as np

from gomoku.ai.model import (
    GomokuNet,
    encode_position,
    load_model,
    save_model,
    symmetry_transforms,
)
from gomoku.core.board import Board
from gomoku.core.enums import Player


def test_encode_position_player_perspective() -> None:
    board = Board(15)
    board.place(7, 7, Player.BLACK)
    board.place(7, 8, Player.WHITE)
    board.place(6, 7, Player.BLACK)

    planes = encode_position(board, Player.BLACK)

    assert planes.shape == (2, 15, 15)
    assert planes.dtype == np.float32
    assert planes[0][7][7] == 1.0
    assert planes[0][6][7] == 1.0
    assert planes[1][7][8] == 1.0
    assert planes[0][7][8] == 0.0
    assert planes[1][7][7] == 0.0
    assert planes.sum() == 3.0

    swapped = encode_position(board, Player.WHITE)
    assert swapped[0][7][8] == 1.0
    assert swapped[1][7][7] == 1.0


def test_symmetry_transforms_are_eight_valid_permutations() -> None:
    perms = symmetry_transforms(15)

    assert len(perms) == 8
    identity = np.arange(15 * 15)
    for perm in perms:
        assert np.array_equal(np.sort(perm), identity)
    assert np.array_equal(perms[0], identity)
    # rot90 clockwise: cell (r, c) content lands at (c, 14 - r), so the
    # new->old permutation maps new (9, 7) back to old (7, 9).
    source = 7 * 15 + 9
    target = 9 * 15 + (14 - 7)
    assert perms[3][target] == source


def test_symmetry_transforms_preserve_encoded_stones() -> None:
    board = Board(15)
    for row, col, player in (
        (3, 4, Player.BLACK),
        (3, 5, Player.WHITE),
        (10, 11, Player.BLACK),
    ):
        board.place(row, col, player)
    planes = encode_position(board, Player.BLACK).reshape(2, 225)

    for perm in symmetry_transforms(15):
        transformed = planes[:, perm]
        assert transformed.sum() == 3.0
        moved = np.nonzero(transformed[0])[0]
        assert moved.size == 2
        for new_index in moved:
            assert planes[0][perm[new_index]] == 1.0


def test_network_forward_shapes() -> None:
    net = GomokuNet(size=15, blocks=2, channels=8)
    planes = torch.zeros(1, 2, 15, 15)

    policy, value = net(planes)

    assert policy.shape == (1, 225)
    assert value.shape == (1, 1)
    assert -1.0 <= float(value.item()) <= 1.0


def test_save_load_roundtrip(tmp_path) -> None:
    path = tmp_path / "tiny.pt"
    net = GomokuNet(size=15, blocks=2, channels=8)
    net.eval()
    planes = torch.randn(1, 2, 15, 15)
    with torch.no_grad():
        expected_policy, expected_value = net(planes)

    save_model(net, path)
    restored = load_model(path)

    policy, value = restored(planes)
    assert restored.blocks == 2
    assert restored.channels == 8
    assert torch.allclose(policy, expected_policy, atol=1e-6)
    assert torch.allclose(value, expected_value, atol=1e-6)


def test_tiny_overfit_smoke() -> None:
    torch.manual_seed(0)
    net = GomokuNet(size=15, blocks=1, channels=8)
    optimizer = torch.optim.Adam(net.parameters(), lr=1e-2)
    ce_loss = torch.nn.CrossEntropyLoss()
    mse_loss = torch.nn.MSELoss()
    planes = torch.randn(8, 2, 15, 15)
    policies = torch.rand(8, 225)
    policies /= policies.sum(dim=1, keepdim=True)
    outcomes = torch.randint(-1, 2, (8, 1)).float()

    losses = []
    for _ in range(30):
        optimizer.zero_grad()
        logits, value = net(planes)
        loss = ce_loss(logits, policies) + mse_loss(value, outcomes)
        loss.backward()
        optimizer.step()
        losses.append(float(loss.item()))

    assert losses[-1] < losses[0]
