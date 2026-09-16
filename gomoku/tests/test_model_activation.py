import builtins
from pathlib import Path
import sys


SRC_DIR = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SRC_DIR))

import pytest

torch = pytest.importorskip("torch")

from gomoku.ai.debug_snapshot import build_debug_snapshot  # noqa: E402
from gomoku.ai.hard_ai import HardAI  # noqa: E402
from gomoku.ai.hard_ai_config import (  # noqa: E402
    DEFAULT_HARD_AI_CONFIG,
)
from gomoku.ai.model import GomokuNet, save_model  # noqa: E402
from gomoku.ai.model_activation import (  # noqa: E402
    ENV_MODEL_PATH,
    build_hard_ai_provider,
    resolve_env_model_path,
)
from gomoku.ai.model_provider import ModelPolicyValueProvider  # noqa: E402
from gomoku.ai.policy_value import (  # noqa: E402
    HeuristicPolicyValueProvider,
)
from gomoku.core.board import Board  # noqa: E402
from gomoku.core.enums import Player  # noqa: E402
from gomoku.core.game import GomokuGame  # noqa: E402
from gomoku.core.rules import get_valid_moves  # noqa: E402


def _tiny_model(tmp_path, size: int = 15) -> Path:
    path = tmp_path / f"tiny-{size}.pt"
    path.parent.mkdir(parents=True, exist_ok=True)
    save_model(GomokuNet(size=size, blocks=1, channels=4), path)
    return path


def test_resolve_env_model_path() -> None:
    assert resolve_env_model_path({}) is None
    assert resolve_env_model_path({ENV_MODEL_PATH: ""}) is None
    assert resolve_env_model_path({ENV_MODEL_PATH: "   "}) is None
    assert resolve_env_model_path({ENV_MODEL_PATH: " a.pt "}) == "a.pt"


def test_unset_env_stays_heuristic_and_torch_free(
    monkeypatch,
) -> None:
    real_import = builtins.__import__

    def no_torch(name, *args, **kwargs):
        if name == "torch" or name.startswith("torch."):
            raise ModuleNotFoundError("No module named 'torch'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_torch)
    monkeypatch.delenv(ENV_MODEL_PATH, raising=False)

    ai = HardAI(Player.WHITE)

    assert isinstance(ai.provider, HeuristicPolicyValueProvider)
    assert ai.provider_type == "heuristic"
    assert ai.provider_model_path is None
    assert ai.provider_note == ""
    assert ai.last_search_stats.provider_type == "heuristic"


def test_env_model_path_activates_model(tmp_path, monkeypatch) -> None:
    model_path = _tiny_model(tmp_path)
    monkeypatch.setenv(ENV_MODEL_PATH, str(model_path))

    ai = HardAI(Player.WHITE)

    assert isinstance(ai.provider, ModelPolicyValueProvider)
    assert ai.provider_type == "model"
    assert ai.provider_model_path == str(model_path)
    assert "size=15" in ai.provider_note
    assert ai.provider.arch_info() == {
        "size": 15,
        "blocks": 1,
        "channels": 4,
    }
    assert ai.last_search_stats.provider_model_path == str(model_path)

    board = Board(15)
    board.place(7, 7, Player.BLACK)
    move = ai.choose_move(board)
    assert move in get_valid_moves(board)


def test_config_model_path_takes_precedence_over_env(
    tmp_path, monkeypatch
) -> None:
    from dataclasses import replace

    config_model = _tiny_model(tmp_path / "cfg")
    env_model = _tiny_model(tmp_path / "env")
    monkeypatch.setenv(ENV_MODEL_PATH, str(env_model))
    config = replace(
        DEFAULT_HARD_AI_CONFIG, model_path=str(config_model)
    )

    ai = HardAI(Player.WHITE, config=config)

    assert isinstance(ai.provider, ModelPolicyValueProvider)
    assert ai.provider_model_path == str(config_model)


def test_invalid_path_falls_back_with_warning(
    tmp_path, monkeypatch, capsys
) -> None:
    missing = tmp_path / "does-not-exist.pt"
    monkeypatch.setenv(ENV_MODEL_PATH, str(missing))

    ai = HardAI(Player.WHITE)

    assert isinstance(ai.provider, HeuristicPolicyValueProvider)
    assert ai.provider_type == "heuristic"
    assert ai.provider_model_path is None
    assert "does-not-exist.pt" in ai.provider_note
    assert ai.last_search_stats.provider_note == ai.provider_note
    warning = capsys.readouterr().err
    assert "does-not-exist.pt" in warning
    assert "heuristic" in warning


def test_incompatible_board_size_falls_back(tmp_path, monkeypatch) -> None:
    model_path = _tiny_model(tmp_path, size=9)
    monkeypatch.setenv(ENV_MODEL_PATH, str(model_path))

    ai = HardAI(Player.WHITE)

    assert isinstance(ai.provider, HeuristicPolicyValueProvider)
    assert ai.provider_type == "heuristic"
    assert "board size" in ai.provider_note


def test_torch_unavailable_falls_back(tmp_path, monkeypatch) -> None:
    model_path = _tiny_model(tmp_path)
    monkeypatch.setenv(ENV_MODEL_PATH, str(model_path))

    real_import = builtins.__import__

    def no_torch(name, *args, **kwargs):
        if name == "torch" or name.startswith("torch."):
            raise ModuleNotFoundError("No module named 'torch'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_torch)

    selection = build_hard_ai_provider(DEFAULT_HARD_AI_CONFIG)

    assert selection.provider_type == "heuristic"
    assert isinstance(selection.provider, HeuristicPolicyValueProvider)
    assert "PyTorch" in selection.note


def test_injected_provider_wins_over_env(tmp_path, monkeypatch) -> None:
    model_path = _tiny_model(tmp_path)
    monkeypatch.setenv(ENV_MODEL_PATH, str(model_path))
    injected = HeuristicPolicyValueProvider(DEFAULT_HARD_AI_CONFIG)

    ai = HardAI(Player.WHITE, provider=injected)

    assert ai.provider is injected
    assert ai.provider_type == "HeuristicPolicyValueProvider"
    assert ai.provider_model_path is None
    assert ai.provider_note == "injected provider"


def test_debug_snapshot_exposes_provider_block(tmp_path, monkeypatch) -> None:
    model_path = _tiny_model(tmp_path)
    monkeypatch.setenv(ENV_MODEL_PATH, str(model_path))
    ai = HardAI(Player.WHITE)

    snapshot = build_debug_snapshot(
        GomokuGame(),
        mode="human_vs_ai",
        ai_player=Player.WHITE,
        ai_difficulty="hard",
        ai=ai,
    )

    block = snapshot["hard_ai"]["provider"]
    assert block == {
        "type": "model",
        "model_path": str(model_path),
        "note": ai.provider_note,
        "arch": {"size": 15, "blocks": 1, "channels": 4},
    }
    stats = snapshot["hard_ai"]["search_stats"]
    assert stats["provider_type"] == "model"
    assert stats["provider_model_path"] == str(model_path)

    monkeypatch.delenv(ENV_MODEL_PATH)
    heuristic_snapshot = build_debug_snapshot(
        GomokuGame(),
        mode="human_vs_ai",
        ai_player=Player.WHITE,
        ai_difficulty="hard",
        ai=HardAI(Player.WHITE),
    )
    heuristic_block = heuristic_snapshot["hard_ai"]["provider"]
    assert heuristic_block["type"] == "heuristic"
    assert heuristic_block["model_path"] is None
    assert heuristic_block["arch"] is None
