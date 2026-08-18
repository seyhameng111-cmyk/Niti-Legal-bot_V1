from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LawOption:
    """Public law metadata shown in Telegram and sent back to GAS."""

    id: str
    title: str
    button_label: str
    emoji: str = "⚖️"
    sort_order: int = 0

    @property
    def button_text(self) -> str:
        label = self.button_label or self.title
        return f"{self.emoji} {label}".strip()
