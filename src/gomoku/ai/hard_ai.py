"""Deterministic HardAI: tactical engine (VCF/VCT/defense) + MCTS fallback.

Decision pipeline (per ``choose_move``)
---------------------------------------
1. Immediate self win (``immediate_win``).
2. VCF slice — verified four-chain win.
3. VCT slice — verified win including open/jump threes.
4. Immediate opponent win block.
5. Tactical defense — verified reply to an opponent forcing chain.
6. MCTS fallback with all remaining budget, tactical cells as priorities.

Timeouts are inconclusive and never become moves; the whole pipeline runs
against one hard deadline plus the safety margin and never raises: on
deadline, cancellation or any unexpected error a legal center-nearest move
is returned. All stages always run (in budget order); each stage checks
the shared deadline and cancel event at every probe point.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, replace

from gomoku.ai.hard_ai_config import DEFAULT_HARD_AI_CONFIG, HardAIConfig
from gomoku.ai.mcts import MCTS
from gomoku.ai.model_activation import build_hard_ai_provider
from gomoku.ai.policy_value import PolicyValueProvider
from gomoku.ai.threat_search import (
    MODE_AUTO,
    MODE_VCF,
    MODE_VCT,
    SearchStatus,
    ThreatSearch,
)
from gomoku.ai.zobrist import ZobristTable
from gomoku.core.board import Board
from gomoku.core.enums import Player
from gomoku.core.rules import get_valid_moves

Move = tuple[int, int]

REASON_IMMEDIATE_WIN = "immediate_win"
REASON_VCF = "vcf_forced_win"
REASON_VCT = "vct_forced_win"
REASON_IMMEDIATE_BLOCK = "immediate_block"
REASON_TACTICAL_DEFENSE = "tactical_defense"
REASON_MCTS = "mcts_fallback"
REASON_TIMEOUT = "timeout_fallback"
REASON_ERROR = "error_fallback"


class HardAITimeout(RuntimeError):
    """Internal cooperative deadline signal; never escapes HardAI."""


@dataclass(frozen=True)
class HardAISearchStats:
    """JSON-safe summary of the last HardAI decision."""

    decision_reason: str = "not_searched"
    selected_move: Move | None = None
    elapsed_ms: float = 0.0
    timed_out: bool = False

    immediate_status: str = ""
    immediate_elapsed_ms: float = 0.0

    vcf_status: str = ""
    vcf_nodes: int = 0
    vcf_elapsed_ms: float = 0.0
    vcf_proof: tuple[Move, ...] = ()

    vct_status: str = ""
    vct_nodes: int = 0
    vct_elapsed_ms: float = 0.0
    vct_proof: tuple[Move, ...] = ()

    defense_status: str = ""
    defense_move: Move | None = None
    defense_elapsed_ms: float = 0.0
    defense_chain: tuple[Move, ...] = ()

    mcts_simulations: int = 0
    mcts_root_visits: int = 0
    mcts_elapsed_ms: float = 0.0
    mcts_value: float = 0.5
    mcts_timed_out: bool = False
    mcts_reuse_plies: int = 0
    mcts_root_noise: bool = False
    root_moves: tuple[tuple[Move, int, float], ...] = ()

    provider_type: str = "heuristic"
    provider_model_path: str | None = None
    provider_note: str = ""


class HardAI:
    """NormalAI-compatible synchronous choose_move with the hard pipeline."""

    def __init__(
        self,
        player: Player | int = Player.WHITE,
        *,
        config: HardAIConfig = DEFAULT_HARD_AI_CONFIG,
        clock: Callable[[], float] = time.monotonic,
        provider: PolicyValueProvider | None = None,
    ) -> None:
        self.player = Player(player)
        if self.player == Player.EMPTY:
            raise ValueError("HardAI player cannot be empty.")
        self.config = config
        self.clock = clock
        zobrist = ZobristTable(config.board_size, config.zobrist_seed)
        self.threat = ThreatSearch(config, zobrist, clock=clock)
        selection = build_hard_ai_provider(config, injected=provider)
        self.provider = selection.provider
        self.provider_type = selection.provider_type
        self.provider_model_path = selection.model_path
        self.provider_note = selection.note
        self.mcts = MCTS(config, self.provider, clock=clock)
        self._lock = threading.Lock()
        self.last_search_stats = self._new_stats()

    # ------------------------------------------------------------------ API

    def choose_move(
        self,
        board: Board,
        player: Player | int | None = None,
        last_opponent_move: Move | None = None,
        cancel_event: threading.Event | None = None,
    ) -> Move | None:
        with self._lock:
            return self._choose_move(
                board, player, last_opponent_move, cancel_event
            )

    def _choose_move(
        self,
        board: Board,
        player: Player | int | None,
        last_opponent_move: Move | None,
        cancel_event: threading.Event | None,
    ) -> Move | None:
        del last_opponent_move  # The complete board is the source of truth.
        valid_moves = get_valid_moves(board)
        if not valid_moves:
            self.last_search_stats = self._new_stats()
            return None
        try:
            me = self.player if player is None else Player(player)
        except ValueError:
            me = self.player
        if me == Player.EMPTY:
            me = self.player

        started = self.clock()
        usable_ms = max(
            0.0,
            float(self.config.time_limit_ms - self.config.time_safety_margin_ms),
        )
        deadline = started + usable_ms / 1000.0
        fallback = min(valid_moves, key=lambda move: self._center_key(move))
        stats = self._new_stats()
        try:
            move, stats = self._decide(
                board,
                me,
                deadline,
                cancel_event,
                usable_ms,
                stats,
            )
        except HardAITimeout:
            move = None
            stats = replace(stats, timed_out=True)
            stats = replace(stats, decision_reason=REASON_TIMEOUT)
        except Exception:
            move = None
            stats = replace(stats, decision_reason=REASON_ERROR)
        final_move = move if move is not None else fallback
        stats = replace(
            stats,
            selected_move=final_move,
            elapsed_ms=max(0.0, (self.clock() - started) * 1000.0),
        )
        self.last_search_stats = stats
        return final_move

    # ------------------------------------------------------------- pipeline

    def _decide(
        self,
        board: Board,
        me: Player,
        deadline: float,
        cancel_event: threading.Event | None,
        usable_ms: float,
        stats: HardAISearchStats,
    ) -> tuple[Move, HardAISearchStats]:
        opponent = me.opponent

        # 1. Immediate self win.
        stage_started = self.clock()
        wins = self.threat.immediate_win(board, me)
        stats = replace(
            stats,
            immediate_status="found" if wins else "none",
            immediate_elapsed_ms=self._elapsed_ms(stage_started),
        )
        if wins:
            return wins[0], replace(stats, decision_reason=REASON_IMMEDIATE_WIN)

        # 2. VCF slice.
        vcf_ms = self._stage_budget(deadline, usable_ms,
                                    self.config.vcf_time_fraction)
        if vcf_ms > 0:
            stage_started = self.clock()
            vcf = self.threat.find_forcing_win(
                board,
                me,
                mode=MODE_VCF,
                time_budget_ms=vcf_ms,
                cancel_event=cancel_event,
            )
            stats = replace(
                stats,
                vcf_status=vcf.status.value,
                vcf_nodes=vcf.nodes,
                vcf_elapsed_ms=self._elapsed_ms(stage_started),
                vcf_proof=vcf.attacker_moves,
            )
            if vcf.status == SearchStatus.FOUND and vcf.first_move:
                return vcf.first_move, replace(
                    stats, decision_reason=REASON_VCF
                )
            self._check(deadline, cancel_event)

        # 3. VCT slice.
        vct_ms = self._stage_budget(deadline, usable_ms,
                                    self.config.vct_time_fraction)
        if vct_ms > 0:
            stage_started = self.clock()
            vct = self.threat.find_forcing_win(
                board,
                me,
                mode=MODE_VCT,
                time_budget_ms=vct_ms,
                cancel_event=cancel_event,
            )
            stats = replace(
                stats,
                vct_status=vct.status.value,
                vct_nodes=vct.nodes,
                vct_elapsed_ms=self._elapsed_ms(stage_started),
                vct_proof=vct.attacker_moves,
            )
            if vct.status == SearchStatus.FOUND and vct.first_move:
                return vct.first_move, replace(
                    stats, decision_reason=REASON_VCT
                )
            self._check(deadline, cancel_event)

        # 4. Immediate opponent win block.
        stage_started = self.clock()
        opponent_wins = self.threat.immediate_win(board, opponent)
        stats = replace(
            stats,
            immediate_elapsed_ms=stats.immediate_elapsed_ms
            + self._elapsed_ms(stage_started),
        )
        if opponent_wins:
            return opponent_wins[0], replace(
                stats, decision_reason=REASON_IMMEDIATE_BLOCK
            )

        # 5. Tactical defense against a verified opponent chain.
        remaining = max(0.0, (deadline - self.clock()) * 1000.0)
        defense_ms = remaining * self.config.defense_time_fraction
        if defense_ms > 0:
            find_ms = defense_ms * (
                1.0 - self.config.defense_verify_budget_fraction
            )
            verify_ms = defense_ms - find_ms
            stage_started = self.clock()
            chain = self.threat.find_forcing_win(
                board,
                opponent,
                mode=MODE_AUTO,
                time_budget_ms=find_ms,
                cancel_event=cancel_event,
            )
            stats = replace(
                stats, defense_chain=chain.attacker_moves
            )
            if chain.status == SearchStatus.FOUND and chain.attacker_moves:
                self._check(deadline, cancel_event)
                defense = self.threat.find_forced_defense(
                    board,
                    me,
                    chain.attacker_moves,
                    time_budget_ms=verify_ms,
                    cancel_event=cancel_event,
                )
                stats = replace(
                    stats,
                    defense_status=defense.status.value,
                    defense_elapsed_ms=self._elapsed_ms(stage_started),
                    defense_move=(
                        defense.forced_defenses[0]
                        if defense.forced_defenses
                        else None
                    ),
                )
                if (
                    defense.status == SearchStatus.FOUND
                    and defense.forced_defenses
                ):
                    return defense.forced_defenses[0], replace(
                        stats, decision_reason=REASON_TACTICAL_DEFENSE
                    )
                stats = replace(
                    stats,
                    defense_elapsed_ms=self._elapsed_ms(stage_started),
                )
            self._check(deadline, cancel_event)

        # 6. MCTS fallback with the remaining budget.
        remaining = max(0.0, (deadline - self.clock()) * 1000.0)
        if remaining < self.config.mcts_min_time_ms:
            raise HardAITimeout
        priority = tuple(
            sorted(set(opponent_wins) | set(stats.defense_chain))
        )
        mcts = self.mcts.search(
            board,
            me,
            time_budget_ms=remaining,
            cancel_event=cancel_event,
            priority_moves=priority,
        )
        stats = replace(
            stats,
            mcts_simulations=mcts.simulations,
            mcts_root_visits=mcts.root_visits,
            mcts_elapsed_ms=mcts.elapsed_ms,
            mcts_value=mcts.value,
            mcts_timed_out=mcts.timed_out,
            mcts_reuse_plies=mcts.reuse_plies,
            mcts_root_noise=mcts.root_noise_applied,
            root_moves=tuple(
                (item.move, item.visits, item.value)
                for item in mcts.root_moves
            ),
        )
        if mcts.move is not None:
            return mcts.move, replace(stats, decision_reason=REASON_MCTS)
        raise HardAITimeout

    # ------------------------------------------------------------- helpers

    def _new_stats(self) -> HardAISearchStats:
        return HardAISearchStats(
            provider_type=self.provider_type,
            provider_model_path=self.provider_model_path,
            provider_note=self.provider_note,
        )

    def _stage_budget(
        self, deadline: float, usable_ms: float, fraction: float
    ) -> float:
        remaining = max(0.0, (deadline - self.clock()) * 1000.0)
        return min(usable_ms * fraction, remaining)

    def _check(
        self,
        deadline: float,
        cancel_event: threading.Event | None,
    ) -> None:
        if (cancel_event is not None and cancel_event.is_set()) or (
            self.clock() >= deadline
        ):
            raise HardAITimeout

    def _elapsed_ms(self, stage_started: float) -> float:
        return max(0.0, (self.clock() - stage_started) * 1000.0)

    def _center_key(self, move: Move) -> tuple:
        center = (self.config.board_size - 1) / 2
        return (
            max(abs(move[0] - center), abs(move[1] - center)),
            move[0],
            move[1],
        )
