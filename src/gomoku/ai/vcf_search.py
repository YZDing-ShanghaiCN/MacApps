"""Bounded victory-by-continuous-fours tactical search."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass

from gomoku.ai.candidate_generator import CandidateGenerator
from gomoku.ai.normal_ai_config import NormalAIConfig
from gomoku.ai.search_position import SearchPosition
from gomoku.core.enums import Player
from gomoku.core.rules import check_win


Move = tuple[int, int]


class VCFTimeout(RuntimeError):
    pass


@dataclass(frozen=True)
class VCFProof:
    first_move: Move
    attacker_moves: tuple[Move, ...]
    forced_defenses: tuple[Move, ...] = ()
    winning_points: tuple[Move, ...] = ()

    @property
    def critical_moves(self) -> frozenset[Move]:
        return frozenset(
            self.attacker_moves + self.forced_defenses + self.winning_points
        )


class VCFSearch:
    """Find a forced win made only of four-producing attacking moves."""

    def __init__(
        self,
        config: NormalAIConfig,
        candidates: CandidateGenerator,
    ) -> None:
        self.config = config
        self.candidates = candidates
        self.nodes = 0
        self.tt_hits = 0
        self._proof_table: OrderedDict[
            tuple[int, Player, int], VCFProof | None
        ] = OrderedDict()
        self.last_proof: VCFProof | None = None
        self.last_defensive_proof_candidates: tuple[Move, ...] = ()

    def find_winning_move(
        self,
        position: SearchPosition,
        attacker: Player,
        timeout_check: Callable[[], None],
    ) -> Move | None:
        self.nodes = 0
        self.tt_hits = 0
        self.last_proof = self._find_winning_proof(
            position,
            attacker,
            timeout_check,
        )
        return self.last_proof.first_move if self.last_proof is not None else None

    def find_defensive_moves(
        self,
        position: SearchPosition,
        defender: Player,
        timeout_check: Callable[[], None],
    ) -> tuple[bool, tuple[Move, ...]]:
        """Return whether the opponent has VCF and moves that break the proof."""

        self.nodes = 0
        self.tt_hits = 0
        self.last_defensive_proof_candidates = ()
        if position.current_player != defender:
            return False, ()
        attacker = defender.opponent
        position.toggle_side_to_move()
        try:
            proof = self._find_winning_proof(
                position,
                attacker,
                timeout_check,
            )
        finally:
            position.toggle_side_to_move()
        if proof is None:
            return False, ()

        proof_candidates = tuple(
            move
            for move in sorted(proof.critical_moves)
            if position.is_empty(*move)
        )
        self.last_defensive_proof_candidates = proof_candidates
        ordinary_defenses = self.candidates.generate(
            position,
            root=True,
            timeout_check=timeout_check,
        )
        limit = max(0, self.config.vcf_defense_max_candidates)
        proof_candidate_set = set(proof_candidates)
        defenses = list(proof_candidates) + [
            move
            for move in ordinary_defenses
            if move not in proof_candidate_set
        ][:limit]
        safe_moves: list[Move] = []
        for move in defenses:
            timeout_check()
            position.make_move(*move)
            try:
                last = position.last_move
                if last is not None and check_win(
                    position,
                    last.row,
                    last.col,
                    last.player,
                ):
                    safe_moves.append(move)
                    continue
                continuation = self._find_winning_proof(
                    position,
                    attacker,
                    timeout_check,
                )
                if continuation is None:
                    safe_moves.append(move)
            finally:
                position.undo_move()
        return True, tuple(safe_moves)

    def _find_winning_proof(
        self,
        position: SearchPosition,
        attacker: Player,
        timeout_check: Callable[[], None],
    ) -> VCFProof | None:
        if position.current_player != attacker:
            return None
        return self._search_attacker(
            position,
            attacker,
            self.config.vcf_max_depth,
            timeout_check,
        )

    def _search_attacker(
        self,
        position: SearchPosition,
        attacker: Player,
        remaining_depth: int,
        timeout_check: Callable[[], None],
    ) -> VCFProof | None:
        timeout_check()
        self.nodes += 1
        if remaining_depth <= 0:
            return None
        cache_key = (position.hash_key, attacker, remaining_depth)
        if cache_key in self._proof_table:
            self.tt_hits += 1
            cached = self._proof_table[cache_key]
            self._proof_table.move_to_end(cache_key)
            return cached

        moves = self.candidates.generate(
            position,
            root=False,
            timeout_check=timeout_check,
        )
        for move in moves:
            timeout_check()
            position.make_move(*move)
            try:
                last = position.last_move
                if last is not None and check_win(
                    position,
                    last.row,
                    last.col,
                    last.player,
                ):
                    proof = VCFProof(move, (move,))
                    self._store(cache_key, proof)
                    return proof

                defender = position.current_player
                defender_wins = self.candidates.immediate_wins(
                    position,
                    defender,
                    timeout_check,
                )
                attacker_wins = self.candidates.immediate_wins(
                    position,
                    attacker,
                    timeout_check,
                )
                if defender_wins or not attacker_wins:
                    continue
                if len(attacker_wins) >= 2:
                    proof = VCFProof(
                        move,
                        (move,),
                        winning_points=tuple(attacker_wins),
                    )
                    self._store(cache_key, proof)
                    return proof

                forced_block = attacker_wins[0]
                position.make_move(*forced_block)
                try:
                    continuation = self._search_attacker(
                        position,
                        attacker,
                        remaining_depth - 2,
                        timeout_check,
                    )
                    if continuation is not None:
                        proof = VCFProof(
                            first_move=move,
                            attacker_moves=(move,) + continuation.attacker_moves,
                            forced_defenses=(forced_block,)
                            + continuation.forced_defenses,
                            winning_points=continuation.winning_points,
                        )
                        self._store(cache_key, proof)
                        return proof
                finally:
                    position.undo_move()
            finally:
                position.undo_move()

        self._store(cache_key, None)
        return None

    def clear(self) -> None:
        self._proof_table.clear()

    @property
    def table_size(self) -> int:
        return len(self._proof_table)

    def _store(
        self,
        key: tuple[int, Player, int],
        proof: VCFProof | None,
    ) -> None:
        capacity = max(0, self.config.vcf_transposition_capacity)
        if capacity == 0:
            return
        self._proof_table[key] = proof
        self._proof_table.move_to_end(key)
        while len(self._proof_table) > capacity:
            self._proof_table.popitem(last=False)
