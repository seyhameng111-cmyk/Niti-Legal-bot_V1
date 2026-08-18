from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import Settings
from app.models import LawOption
from app.state import AnswerMode


class GasError(RuntimeError):
    """Safe, user-displayable GAS integration error."""


@dataclass(frozen=True, slots=True)
class TelegramContext:
    chat_id: int
    user_id: int
    username: str | None
    first_name: str | None
    update_id: int | None


class GasClient:
    def __init__(
        self, settings: Settings, client: httpx.AsyncClient | None = None
    ) -> None:
        self.settings = settings
        timeout = httpx.Timeout(
            connect=min(15.0, settings.gas_timeout_seconds),
            read=settings.gas_timeout_seconds,
            write=30.0,
            pool=15.0,
        )
        self._client = client or httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "NITI-Telegram-Router/2.0"},
        )
        self._owns_client = client is None
        self._catalog_cache: list[LawOption] = []
        self._catalog_cached_at = 0.0
        self._catalog_lock = asyncio.Lock()

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def list_laws(self, *, force_refresh: bool = False) -> list[LawOption]:
        ttl = self.settings.law_catalog_cache_seconds
        now = time.monotonic()
        if (
            not force_refresh
            and self._catalog_cache
            and now - self._catalog_cached_at < ttl
        ):
            return list(self._catalog_cache)

        async with self._catalog_lock:
            now = time.monotonic()
            if (
                not force_refresh
                and self._catalog_cache
                and now - self._catalog_cached_at < ttl
            ):
                return list(self._catalog_cache)

            payload: dict[str, Any] = {
                "action": "list_laws",
                "source": "telegram",
            }
            self._add_api_key(payload)
            data = await self._post_json(
                self.settings.resolved_gas_catalog_url,
                payload,
                operation="បញ្ជីច្បាប់",
            )

            if data.get("ok") is False:
                reason = str(data.get("error") or "GAS reported an error")[:500]
                raise GasError(f"មិនអាចទាញបញ្ជីច្បាប់បាន៖ {reason}")

            raw_laws = data.get("laws")
            if not isinstance(raw_laws, list):
                raise GasError("LAW_CATALOG response មិនមាន field «laws» ជា array ទេ។")

            laws: list[LawOption] = []
            seen_ids: set[str] = set()
            for index, item in enumerate(raw_laws):
                law = self._parse_law(item, index)
                if law.id in seen_ids:
                    raise GasError(f"LAW_CATALOG មាន law_id ស្ទួន៖ {law.id}")
                seen_ids.add(law.id)
                laws.append(law)

            laws.sort(key=lambda law: (law.sort_order, law.title.casefold()))
            self._catalog_cache = laws
            self._catalog_cached_at = time.monotonic()
            return list(laws)

    async def ask(
        self,
        mode: AnswerMode,
        question: str,
        law: LawOption,
        context: TelegramContext,
    ) -> str:
        url = (
            self.settings.gas_literal_url
            if mode is AnswerMode.LITERAL
            else self.settings.gas_explain_url
        )
        response_path = (
            self.settings.gas_literal_response_path
            if mode is AnswerMode.LITERAL
            else self.settings.gas_explain_response_path
        )
        payload: dict[str, Any] = {
            "action": "ask",
            self.settings.gas_question_field: question,
            "mode": mode.value,
            "model": self.settings.gemini_model,
            "lawId": law.id,
            "lawTitle": law.title,
            "source": "telegram",
            "telegram": {
                "chatId": context.chat_id,
                "userId": context.user_id,
                "username": context.username,
                "firstName": context.first_name,
                "updateId": context.update_id,
            },
        }
        self._add_api_key(payload)

        response = await self._post(url, payload, operation="ចម្លើយច្បាប់")
        answer = self._extract_answer(response, response_path)
        if not answer.strip():
            raise GasError("ប្រព័ន្ធចំណេះដឹងមិនបានផ្ដល់ចម្លើយមកទេ។")
        return answer.strip()

    def _add_api_key(self, payload: dict[str, Any]) -> None:
        if self.settings.gas_api_key:
            payload[self.settings.gas_api_key_field] = (
                self.settings.gas_api_key.get_secret_value()
            )

    async def _post_json(
        self, url: str, payload: dict[str, Any], *, operation: str
    ) -> dict[str, Any]:
        response = await self._post(url, payload, operation=operation)
        raw = response.text.strip()
        if self._looks_like_html(raw):
            raise GasError(
                "GAS បានត្រឡប់ HTML។ ពិនិត្យ /exec URL, Web App access និង doPost។"
            )
        try:
            data = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise GasError(f"GAS {operation} មិនបានត្រឡប់ JSON ត្រឹមត្រូវទេ។") from exc
        if not isinstance(data, dict):
            raise GasError(f"GAS {operation} ត្រូវត្រឡប់ JSON object។")
        return data

    async def _post(
        self, url: str, payload: dict[str, Any], *, operation: str
    ) -> httpx.Response:
        try:
            response = await self._client.post(url, json=payload)
            response.raise_for_status()
            return response
        except httpx.TimeoutException as exc:
            raise GasError(f"ប្រព័ន្ធ {operation} ឆ្លើយតបយឺតពេក។ សូមសាកល្បងម្ដងទៀត។") from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            raise GasError(f"ប្រព័ន្ធ {operation} មានបញ្ហា (HTTP {status})។") from exc
        except httpx.HTTPError as exc:
            raise GasError(f"មិនអាចភ្ជាប់ទៅប្រព័ន្ធ {operation} បានទេ។") from exc

    @staticmethod
    def _parse_law(item: Any, index: int) -> LawOption:
        if not isinstance(item, dict):
            raise GasError(f"LAW_CATALOG item {index + 1} មិនមែនជា object។")

        law_id = str(item.get("id") or item.get("lawId") or "").strip()
        title = str(
            item.get("title") or item.get("titleKm") or item.get("lawTitle") or ""
        ).strip()
        button_label = str(item.get("buttonLabel") or title).strip()
        emoji = str(item.get("emoji") or "⚖️").strip()[:8]

        if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", law_id):
            shown_id = law_id or str(index + 1)
            raise GasError(
                f"LAW_CATALOG law_id «{shown_id}» ត្រូវមានតែ "
                "A-Z, 0-9, _ ឬ - និងមិនលើស 40 តួ។"
            )
        if not title:
            raise GasError(f"LAW_CATALOG law_id «{law_id}» មិនមាន title។")

        try:
            sort_order = int(item.get("sortOrder", index))
        except (TypeError, ValueError):
            sort_order = index

        return LawOption(
            id=law_id,
            title=title[:200],
            button_label=button_label[:64],
            emoji=emoji or "⚖️",
            sort_order=sort_order,
        )

    @classmethod
    def _extract_answer(cls, response: httpx.Response, response_path: str) -> str:
        content_type = response.headers.get("content-type", "").lower()
        raw = response.text.strip()

        data: Any = None
        if "json" in content_type or raw.startswith(("{", "[", '"')):
            try:
                data = response.json()
            except (json.JSONDecodeError, ValueError):
                data = None

        if data is not None:
            if isinstance(data, dict) and data.get("ok") is False:
                reason = str(data.get("error") or "GAS reported an error")[:500]
                raise GasError(f"ប្រព័ន្ធចំណេះដឹងបានរាយការណ៍បញ្ហា៖ {reason}")

            value = cls._get_path(data, response_path)
            if value is None:
                for path in (
                    "answer",
                    "response",
                    "text",
                    "message",
                    "result",
                    "output",
                    "data",
                    "data.answer",
                    "data.text",
                    "data.response",
                    "result.answer",
                    "result.text",
                ):
                    value = cls._get_path(data, path)
                    if value is not None:
                        break
            if isinstance(value, str):
                return value
            if value is not None:
                return json.dumps(value, ensure_ascii=False)
            if isinstance(data, str):
                return data
            raise GasError(
                f"GAS JSON response មិនមាន field «{response_path}» ដែលបានកំណត់ទេ។"
            )

        if cls._looks_like_html(raw):
            raise GasError(
                "GAS បានត្រឡប់ទំព័រ HTML។ សូមពិនិត្យ Web App access និង Deployment URL។"
            )
        return raw

    @staticmethod
    def _looks_like_html(raw: str) -> bool:
        lowered = raw[:500].lower()
        return "<html" in lowered or "<!doctype html" in lowered

    @staticmethod
    def _get_path(data: Any, dotted_path: str) -> Any:
        current = data
        for key in filter(None, dotted_path.split(".")):
            if isinstance(current, dict) and key in current:
                current = current[key]
                continue
            if isinstance(current, list) and key.isdigit():
                index = int(key)
                if 0 <= index < len(current):
                    current = current[index]
                    continue
            return None
        return current
