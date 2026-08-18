from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from app.models import LawOption


class AnswerMode(StrEnum):
    LITERAL = "literal"
    EXPLAIN = "explain"


@dataclass(frozen=True, slots=True)
class UserSession:
    law_id: str | None = None
    law_title: str | None = None
    law_button_label: str | None = None
    law_emoji: str = "⚖️"
    mode: AnswerMode | None = None
    updated_at: datetime | None = None

    @property
    def has_law(self) -> bool:
        return bool(self.law_id and self.law_title)

    def as_law_option(self) -> LawOption | None:
        if not self.has_law:
            return None
        return LawOption(
            id=str(self.law_id),
            title=str(self.law_title),
            button_label=self.law_button_label or str(self.law_title),
            emoji=self.law_emoji,
        )


class MemoryStateStore:
    """MVP state store. Replace with PostgreSQL without changing handlers."""

    def __init__(self) -> None:
        self._items: dict[tuple[int, int], UserSession] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _key(chat_id: int, user_id: int) -> tuple[int, int]:
        return chat_id, user_id

    async def get_session(self, chat_id: int, user_id: int) -> UserSession:
        async with self._lock:
            return self._items.get(self._key(chat_id, user_id), UserSession())

    async def get_mode(self, chat_id: int, user_id: int) -> AnswerMode | None:
        return (await self.get_session(chat_id, user_id)).mode

    async def set_law(self, chat_id: int, user_id: int, law: LawOption) -> UserSession:
        # Selecting a law resets the mode so the user confirms both choices.
        session = UserSession(
            law_id=law.id,
            law_title=law.title,
            law_button_label=law.button_label,
            law_emoji=law.emoji,
            mode=None,
            updated_at=datetime.now(UTC),
        )
        async with self._lock:
            self._items[self._key(chat_id, user_id)] = session
        return session

    async def set_mode(
        self, chat_id: int, user_id: int, mode: AnswerMode
    ) -> UserSession:
        async with self._lock:
            key = self._key(chat_id, user_id)
            current = self._items.get(key, UserSession())
            if not current.has_law:
                raise ValueError("A law must be selected before choosing a mode")
            session = UserSession(
                law_id=current.law_id,
                law_title=current.law_title,
                law_button_label=current.law_button_label,
                law_emoji=current.law_emoji,
                mode=mode,
                updated_at=datetime.now(UTC),
            )
            self._items[key] = session
            return session

    async def clear_mode(self, chat_id: int, user_id: int) -> None:
        async with self._lock:
            key = self._key(chat_id, user_id)
            current = self._items.get(key)
            if not current or not current.has_law:
                return
            self._items[key] = UserSession(
                law_id=current.law_id,
                law_title=current.law_title,
                law_button_label=current.law_button_label,
                law_emoji=current.law_emoji,
                mode=None,
                updated_at=datetime.now(UTC),
            )

    async def clear_session(self, chat_id: int, user_id: int) -> None:
        async with self._lock:
            self._items.pop(self._key(chat_id, user_id), None)

    # Backwards-compatible alias used by earlier code/tests.
    async def clear_mode_and_law(self, chat_id: int, user_id: int) -> None:
        await self.clear_session(chat_id, user_id)

    async def count(self) -> int:
        async with self._lock:
            return len(self._items)
