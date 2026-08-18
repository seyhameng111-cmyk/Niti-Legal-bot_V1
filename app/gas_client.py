from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import Settings
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
            headers={"User-Agent": "NITI-Telegram-Router/1.0"},
        )
        self._owns_client = client is None

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def ask(
        self,
        mode: AnswerMode,
        question: str,
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
            self.settings.gas_question_field: question,
            "mode": mode.value,
            "model": self.settings.gemini_model,
            "source": "telegram",
            "telegram": {
                "chatId": context.chat_id,
                "userId": context.user_id,
                "username": context.username,
                "firstName": context.first_name,
                "updateId": context.update_id,
            },
        }
        if self.settings.gas_api_key:
            payload[self.settings.gas_api_key_field] = (
                self.settings.gas_api_key.get_secret_value()
            )

        try:
            response = await self._client.post(url, json=payload)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise GasError("ប្រព័ន្ធចំណេះដឹងឆ្លើយតបយឺតពេក។ សូមសាកល្បងម្ដងទៀត។") from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            raise GasError(f"ប្រព័ន្ធចំណេះដឹងមានបញ្ហា (HTTP {status})។") from exc
        except httpx.HTTPError as exc:
            raise GasError("មិនអាចភ្ជាប់ទៅប្រព័ន្ធចំណេះដឹងបានទេ។") from exc

        answer = self._extract_answer(response, response_path)
        if not answer.strip():
            raise GasError("ប្រព័ន្ធចំណេះដឹងមិនបានផ្ដល់ចម្លើយមកទេ។")
        return answer.strip()

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
                    "data.answer",
                    "data.text",
                    "data.response",
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

        lowered = raw[:300].lower()
        if "<html" in lowered or "<!doctype html" in lowered:
            raise GasError(
                "GAS បានត្រឡប់ទំព័រ HTML។ សូមពិនិត្យ Web App access និង Deployment URL។"
            )
        return raw

    @staticmethod
    def _get_path(data: Any, dotted_path: str) -> Any:
        current = data
        for key in filter(None, dotted_path.split(".")):
            if not isinstance(current, dict) or key not in current:
                return None
            current = current[key]
        return current
