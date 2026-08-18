from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class AnswerMode(StrEnum):
    LITERAL = "literal"
    EXPLAIN = "explain"


@dataclass(frozen=True, slots=True)
class ModeSelection:
    mode: AnswerMode
    selected_at: datetime


class MemoryStateStore:
    """MVP state store. Replace with PostgreSQL without changing handlers."""

    def __init__(self) -> None:
        self._items: dict[tuple[int, int], ModeSelection] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _key(chat_id: int, user_id: int) -> tuple[int, int]:
        return chat_id, user_id

    async def get_mode(self, chat_id: int, user_id: int) -> AnswerMode | None:
        async with self._lock:
            item = self._items.get(self._key(chat_id, user_id))
            return item.mode if item else None

    async def set_mode(
        self, chat_id: int, user_id: int, mode: AnswerMode
    ) -> ModeSelection:
        selection = ModeSelection(mode=mode, selected_at=datetime.now(UTC))
        async with self._lock:
            self._items[self._key(chat_id, user_id)] = selection
        return selection

    async def clear_mode(self, chat_id: int, user_id: int) -> None:
        async with self._lock:
            self._items.pop(self._key(chat_id, user_id), None)

    async def count(self) -> int:
        async with self._lock:
            return len(self._items)
