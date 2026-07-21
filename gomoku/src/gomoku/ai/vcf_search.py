"""Bounded victory-by-continuous-fours tactical search."""

from __future__ import annotations

from collections.abc import Callable

from gomoku.ai.candidate_generator import CandidateGenerator
from gomoku.ai.normal_ai_config import NormalAIConfig
from gomoku.ai.search_position import SearchPosition
from gomoku.core.enums import Player
from gomoku.core.rules import check_win


Move = tuple[int, int]


class VCFTimeout(RuntimeError):
    pass


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
        self._failed: set[tuple[int, int]] = set()

    def find_winning_move(
        self,
        position: SearchPosition,
        attacker: Player,
        timeout_check: Callable[[], None],
    ) -> Move | None:
        self.nodes = 0
        return self._find_winning_move(position, attacker, timeout_check)

    def find_defensive_moves(
        self,
        position: SearchPosition,
        defender: Player,
        timeout_check: Callable[[], None],
    ) -> tuple[bool, tuple[Move, ...]]:
        """Return whether the opponent has VCF and moves that break the proof."""

        self.nodes = 0
        if position.current_player != defender:
            return False, ()
        attacker = defender.opponent
        position.toggle_side_to_move()
        try:
            attacker_move = self._find_winning_move(
                position,
                attacker,
                timeout_check,
            )
        finally:
            position.toggle_side_to_move()
        if attacker_move is None:
            return False, ()

        defenses = self.candidates.generate(
            position,
            root=True,
            timeout_check=timeout_check,
        )
        limit = max(0, self.config.vcf_defense_max_candidates)
        safe_moves: list[Move] = []
        for move in defenses[:limit]:
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
                continuation = self._find_winning_move(
                    position,
                    attacker,
                    timeout_check,
                )
                if continuation is None:
                    safe_moves.append(move)
            finally:
                position.undo_move()
        return True, tuple(safe_moves)

    def _find_winning_move(
        self,
        position: SearchPosition,
        attacker: Player,
        timeout_check: Callable[[], None],
    ) -> Move | None:
        self._failed.clear()
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
    ) -> Move | None:
        timeout_check()
        self.nodes += 1
        if remaining_depth <= 0:
            return None
        cache_key = (position.hash_key, remaining_depth)
        if cache_key in self._failed:
            return None

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
                    return move

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
                    return move

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
                        return move
                finally:
                    position.undo_move()
            finally:
                position.undo_move()

        self._failed.add(cache_key)
        return None
