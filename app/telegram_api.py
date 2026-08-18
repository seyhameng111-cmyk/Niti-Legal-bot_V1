from __future__ import annotations

from typing import Any

import httpx


class TelegramApiError(RuntimeError):
    pass


class TelegramAPI:
    def __init__(self, bot_token: str) -> None:
        self._base_url = f"https://api.telegram.org/bot{bot_token}"
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=15.0))

    async def close(self) -> None:
        await self._client.aclose()

    async def _call(self, method: str, payload: dict[str, Any] | None = None) -> Any:
        try:
            response = await self._client.post(
                f"{self._base_url}/{method}", json=payload or {}
            )
            data = response.json()
        except httpx.HTTPError as exc:
            raise TelegramApiError(f"Telegram API request failed: {method}") from exc
        except ValueError as exc:
            status_code = response.status_code
            raise TelegramApiError(
                f"Telegram API returned invalid JSON: {method} (HTTP {status_code})"
            ) from exc
        if not data.get("ok"):
            description = data.get("description", "Unknown Telegram API error")
            raise TelegramApiError(f"{method}: {description}")
        return data.get("result")

    async def get_me(self) -> dict[str, Any]:
        return await self._call("getMe")

    async def set_webhook(self, url: str, secret_token: str) -> bool:
        return bool(
            await self._call(
                "setWebhook",
                {
                    "url": url,
                    "secret_token": secret_token,
                    "allowed_updates": ["message", "callback_query"],
                    "drop_pending_updates": False,
                    "max_connections": 40,
                },
            )
        )

    async def set_commands(self) -> None:
        await self._call(
            "setMyCommands",
            {
                "commands": [
                    {"command": "start", "description": "បើកបណ្ណាល័យច្បាប់"},
                    {"command": "law", "description": "ជ្រើស ឬប្ដូរច្បាប់"},
                    {"command": "mode", "description": "ប្ដូររបៀបឆ្លើយ"},
                    {"command": "menu", "description": "បើក Menu មេ"},
                    {"command": "help", "description": "របៀបប្រើប្រាស់"},
                ]
            },
        )

    async def set_description(self, brand: str) -> None:
        await self._call(
            "setMyDescription",
            {
                "description": (
                    f"{brand} — ជំនួយការស្រាវជ្រាវច្បាប់ឆ្លាតវៃ។ "
                    "ជ្រើសចម្លើយន័យត្រង់ ឬបែបអធិប្បាយ រួចផ្ញើសំណួររបស់អ្នក។"
                )
            },
        )
        await self._call(
            "setMyShortDescription",
            {"short_description": "ជំនួយការស្រាវជ្រាវច្បាប់ • Direct & Explained"},
        )

    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "link_preview_options": {"is_disabled": True},
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        return await self._call("sendMessage", payload)

    async def edit_message(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any] | bool:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML",
            "link_preview_options": {"is_disabled": True},
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        return await self._call("editMessageText", payload)

    async def answer_callback(
        self, callback_query_id: str, text: str | None = None
    ) -> bool:
        payload: dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        return bool(await self._call("answerCallbackQuery", payload))

    async def send_chat_action(self, chat_id: int, action: str = "typing") -> bool:
        return bool(
            await self._call("sendChatAction", {"chat_id": chat_id, "action": action})
        )
