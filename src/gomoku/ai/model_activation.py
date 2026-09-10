"""Explicit opt-in activation of a trained model for the HardAI.

The shipped game is heuristic-only: a trained policy/value network is used
only when the user configures one, either via ``HardAIConfig.model_path``
or the ``GOMOKU_HARD_AI_MODEL_PATH`` environment variable (an explicit
``HardAI(..., provider=...)`` injection always wins over both). The model
is loaded and validated eagerly at HardAI construction; any failure is
diagnosed once on stderr and the construction falls back to the
deterministic heuristic provider, so a missing or incompatible model can
never break a game.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
import sys

from gomoku.ai.hard_ai_config import HardAIConfig

ENV_MODEL_PATH = "GOMOKU_HARD_AI_MODEL_PATH"

_warned_paths: set[str] = set()


def resolve_env_model_path(environ=None) -> str | None:
    """Return the configured model path from the environment, else None."""

    if environ is None:
        environ = os.environ
    value = environ.get(ENV_MODEL_PATH, "")
    if not value.strip():
        return None
    return value.strip()


@dataclass(frozen=True)
class ProviderSelection:
    """The provider a HardAI ended up with, plus identity diagnostics."""

    provider: object
    provider_type: str
    model_path: str | None
    note: str


def build_hard_ai_provider(
    config: HardAIConfig,
    *,
    injected=None,
) -> ProviderSelection:
    """Pick the HardAI policy/value provider and validate any model eagerly.

    Priority: injected provider, then ``config.model_path``, then the
    environment variable, then the heuristic provider. Model activation
    failures degrade to the heuristic provider with a stderr diagnostic.
    The model provider module (and its numpy/torch imports) is only touched
    when a model path is actually configured, so the heuristic-only game
    keeps running without any ML dependency.
    """

    from gomoku.ai.policy_value import HeuristicPolicyValueProvider

    if injected is not None:
        return ProviderSelection(
            provider=injected,
            provider_type=type(injected).__name__,
            model_path=getattr(injected, "model_path", None),
            note="injected provider",
        )

    model_path = config.model_path or resolve_env_model_path()
    if model_path:
        from gomoku.ai.model_provider import ModelPolicyValueProvider

        try:
            provider = ModelPolicyValueProvider(config, model_path)
            net = provider._ensure_net()
            if net.size != config.board_size:
                raise ValueError(
                    f"model expects board size {net.size}, configured "
                    f"board size is {config.board_size}"
                )
            arch = (
                f"size={net.size}, blocks={net.blocks}, "
                f"channels={net.channels}"
            )
        except Exception as exc:
            note = f"model '{model_path}' unusable: {exc}"
            if model_path not in _warned_paths:
                _warned_paths.add(model_path)
                print(
                    f"[HardAI] {note} Falling back to the heuristic "
                    "provider.",
                    file=sys.stderr,
                )
            return ProviderSelection(
                provider=HeuristicPolicyValueProvider(config),
                provider_type="heuristic",
                model_path=None,
                note=note,
            )
        return ProviderSelection(
            provider=provider,
            provider_type="model",
            model_path=model_path,
            note=f"model loaded: {arch}",
        )

    return ProviderSelection(
        provider=HeuristicPolicyValueProvider(config),
        provider_type="heuristic",
        model_path=None,
        note="",
    )
