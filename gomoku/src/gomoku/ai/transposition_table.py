"""Capacity-bounded transposition table for NormalAI."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class BoundType(str, Enum):
    EXACT = "exact"
    LOWER = "lower"
    UPPER = "upper"


@dataclass(frozen=True)
class TranspositionEntry:
    key: int
    depth: int
    score: int
    bound: BoundType
    best_move: tuple[int, int] | None
    generation: int
    extension_depth: int = 0


class TranspositionTable:
    """A deterministic one-entry-per-bucket table.

    Collisions prefer the current search generation and then deeper entries.
    The fixed bucket array makes the configured capacity a strict upper bound.
    """

    def __init__(self, capacity: int) -> None:
        if capacity <= 0:
            raise ValueError("Transposition table capacity must be positive.")
        self.capacity = capacity
        self._entries: list[TranspositionEntry | None] = [None] * capacity
        self.generation = 0

    def new_generation(self) -> int:
        self.generation += 1
        return self.generation

    def clear(self) -> None:
        self._entries = [None] * self.capacity

    def probe(self, key: int) -> TranspositionEntry | None:
        entry = self._entries[key % self.capacity]
        if entry is not None and entry.key == key:
            return entry
        return None

    def store(self, entry: TranspositionEntry) -> None:
        index = entry.key % self.capacity
        current = self._entries[index]
        if current is None:
            self._entries[index] = entry
            return

        if current.key == entry.key:
            if (
                entry.depth > current.depth
                or entry.extension_depth > current.extension_depth
                or entry.bound == BoundType.EXACT
                or entry.generation > current.generation
            ):
                self._entries[index] = entry
            return

        if (
            entry.generation > current.generation
            or (
                entry.generation == current.generation
                and entry.depth >= current.depth
            )
        ):
            self._entries[index] = entry
