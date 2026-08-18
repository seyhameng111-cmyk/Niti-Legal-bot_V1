from __future__ import annotations

import asyncio
import contextlib
import html
import logging
from collections import defaultdict
from typing import Any

from app import ui
from app.config import Settings
from app.gas_client import GasClient, GasError, TelegramContext
from app.models import LawOption
from app.rate_limit import SlidingWindowRateLimiter
from app.state import AnswerMode, MemoryStateStore
from app.telegram_api import TelegramAPI, TelegramApiError

logger = logging.getLogger(__name__)


class BotHandlers:
    def __init__(
        self,
        settings: Settings,
        telegram: TelegramAPI,
        gas: GasClient,
        state: MemoryStateStore,
        rate_limiter: SlidingWindowRateLimiter,
    ) -> None:
        self.settings = settings
        self.telegram = telegram
        self.gas = gas
        self.state = state
        self.rate_limiter = rate_limiter
        self._question_locks: defaultdict[tuple[int, int], asyncio.Lock] = defaultdict(
            asyncio.Lock
        )

    async def handle(self, update: dict[str, Any]) -> None:
        if callback := update.get("callback_query"):
            await self._handle_callback(callback)
            return
        if message := update.get("message"):
            await self._handle_message(message, update.get("update_id"))

    async def _handle_callback(self, callback: dict[str, Any]) -> None:
        callback_id = str(callback.get("id", ""))
        if callback_id:
            with contextlib.suppress(TelegramApiError):
                await self.telegram.answer_callback(callback_id)

        message = callback.get("message") or {}
        chat_id = (message.get("chat") or {}).get("id")
        message_id = message.get("message_id")
        user = callback.get("from") or {}
        user_id = user.get("id")
        data = str(callback.get("data", ""))
        if not isinstance(chat_id, int) or not isinstance(user_id, int):
            return

        if data == "noop":
            return

        if data == "menu":
            await self._show_law_menu(chat_id, user_id, message_id=message_id)
            return

        if data == "catalog:refresh":
            await self._show_law_menu(
                chat_id,
                user_id,
                message_id=message_id,
                force_refresh=True,
            )
            return

        if data.startswith("laws:page:"):
            try:
                page = int(data.rsplit(":", 1)[1])
            except ValueError:
                page = 0
            await self._show_law_menu(
                chat_id, user_id, message_id=message_id, page=page
            )
            return

        if data.startswith("law:"):
            law_id = data.split(":", 1)[1]
            try:
                laws = await self.gas.list_laws()
                law = next((item for item in laws if item.id == law_id), None)
                if law is None:
                    laws = await self.gas.list_laws(force_refresh=True)
                    law = next((item for item in laws if item.id == law_id), None)
                if law is None:
                    raise GasError("ច្បាប់នេះត្រូវបានដកចេញ ឬបិទពី LAW_CATALOG។")
            except GasError as exc:
                await self._show_catalog_error(chat_id, message_id, str(exc))
                return

            await self.state.set_law(chat_id, user_id, law)
            text, keyboard = ui.mode_menu(self.settings.bot_brand_name, law)
            await self._edit_or_send(chat_id, message_id, text, keyboard)
            return

        if data == "mode:menu":
            await self._show_mode_menu(chat_id, user_id, message_id)
            return

        if data.startswith("mode:"):
            try:
                mode = AnswerMode(data.split(":", 1)[1])
            except ValueError:
                return

            session = await self.state.get_session(chat_id, user_id)
            law = session.as_law_option()
            if law is None:
                await self._show_law_menu(chat_id, user_id, message_id=message_id)
                return

            try:
                await self.state.set_mode(chat_id, user_id, mode)
            except ValueError:
                await self._show_law_menu(chat_id, user_id, message_id=message_id)
                return

            text, keyboard = ui.mode_selected(self.settings.bot_brand_name, law, mode)
            await self._edit_or_send(chat_id, message_id, text, keyboard)
            return

        if data == "help":
            text, keyboard = ui.help_message(self.settings.bot_brand_name)
            await self._edit_or_send(chat_id, message_id, text, keyboard)
            return

        if data == "ask:again":
            session = await self.state.get_session(chat_id, user_id)
            law = session.as_law_option()
            if law is None:
                await self._show_law_menu(chat_id, user_id)
            elif session.mode is None:
                text, keyboard = ui.mode_menu(self.settings.bot_brand_name, law)
                await self.telegram.send_message(chat_id, text, keyboard)
            else:
                text = (
                    "✍️ <b>សូមផ្ញើសំណួរបន្ទាប់</b>\n"
                    f"📘 {html.escape(law.title)}\n"
                    f"🎯 {ui.mode_label(session.mode)}"
                )
                keyboard = {
                    "inline_keyboard": [
                        [
                            {"text": "🎯 ប្ដូរ Mode", "callback_data": "mode:menu"},
                            {"text": "📘 ប្ដូរច្បាប់", "callback_data": "menu"},
                        ]
                    ]
                }
                await self.telegram.send_message(chat_id, text, keyboard)

    async def _handle_message(
        self, message: dict[str, Any], update_id: int | None
    ) -> None:
        chat_id = (message.get("chat") or {}).get("id")
        user = message.get("from") or {}
        user_id = user.get("id")
        if not isinstance(chat_id, int) or not isinstance(user_id, int):
            return

        text = message.get("text")
        if not isinstance(text, str):
            await self.telegram.send_message(
                chat_id,
                "📝 សូមផ្ញើសំណួរជា <b>អត្ថបទ (text)</b>។ ឯកសារ និងសំឡេងមិនទាន់គាំទ្រនៅឡើយ។",
            )
            return
        text = text.strip()
        if not text:
            return

        if text.startswith("/"):
            command = text.split(maxsplit=1)[0].split("@", 1)[0].lower()
            if command in {"/start", "/menu", "/law"}:
                await self._show_law_menu(chat_id, user_id)
                return
            if command == "/mode":
                await self._show_mode_menu(chat_id, user_id)
                return
            if command == "/help":
                help_text, keyboard = ui.help_message(self.settings.bot_brand_name)
                await self.telegram.send_message(chat_id, help_text, keyboard)
                return
            await self.telegram.send_message(
                chat_id, "ពាក្យបញ្ជានេះមិនត្រឹមត្រូវទេ។ ប្រើ /menu ឬ /help។"
            )
            return

        session = await self.state.get_session(chat_id, user_id)
        law = session.as_law_option()
        if law is None:
            await self.telegram.send_message(
                chat_id,
                "🔐 <b>សូមជ្រើសច្បាប់មុនសិន</b>\nប្រើ /law ដើម្បីបើកបណ្ណាល័យច្បាប់។",
            )
            await self._show_law_menu(chat_id, user_id)
            return

        if session.mode is None:
            mode_text, keyboard = ui.mode_menu(self.settings.bot_brand_name, law)
            await self.telegram.send_message(
                chat_id,
                "🎯 <b>សូមជ្រើសរបៀបឆ្លើយមុនសិន</b>\n\n" + mode_text,
                keyboard,
            )
            return

        if len(text) > self.settings.max_question_chars:
            limit = self.settings.max_question_chars
            await self.telegram.send_message(
                chat_id,
                f"សំណួរវែងពេក។ សូមកាត់ឱ្យនៅក្រោម <b>{limit:,}</b> តួអក្សរ។",
            )
            return

        allowed, retry_after = await self.rate_limiter.allow((chat_id, user_id))
        if not allowed:
            await self.telegram.send_message(
                chat_id,
                f"⏱️ អ្នកបានផ្ញើសំណួរញឹកញាប់ពេក។ សូមរង់ចាំប្រហែល <b>{retry_after}</b> វិនាទី។",
            )
            return

        lock = self._question_locks[(chat_id, user_id)]
        if lock.locked():
            await self.telegram.send_message(
                chat_id,
                "⏳ ខ្ញុំកំពុងរៀបចំចម្លើយមុននៅឡើយ។ សូមរង់ចាំចម្លើយនោះសិន។",
            )
            return

        async with lock:
            await self._answer_question(
                chat_id=chat_id,
                user_id=user_id,
                user=user,
                update_id=update_id,
                question=text,
                law=law,
                mode=session.mode,
            )

    async def _show_law_menu(
        self,
        chat_id: int,
        user_id: int,
        *,
        message_id: int | None = None,
        page: int = 0,
        force_refresh: bool = False,
    ) -> None:
        try:
            laws = await self.gas.list_laws(force_refresh=force_refresh)
        except GasError as exc:
            await self._show_catalog_error(chat_id, message_id, str(exc))
            return

        if not laws:
            text, keyboard = ui.empty_law_menu(self.settings.bot_brand_name)
        else:
            session = await self.state.get_session(chat_id, user_id)
            text, keyboard = ui.law_menu(
                self.settings.bot_brand_name,
                laws,
                page=page,
                page_size=self.settings.law_menu_page_size,
                current_law_id=session.law_id,
            )
        await self._edit_or_send(chat_id, message_id, text, keyboard)

    async def _show_mode_menu(
        self, chat_id: int, user_id: int, message_id: int | None = None
    ) -> None:
        session = await self.state.get_session(chat_id, user_id)
        law = session.as_law_option()
        if law is None:
            await self._show_law_menu(chat_id, user_id, message_id=message_id)
            return
        text, keyboard = ui.mode_menu(self.settings.bot_brand_name, law, session.mode)
        await self._edit_or_send(chat_id, message_id, text, keyboard)

    async def _show_catalog_error(
        self, chat_id: int, message_id: int | None, error: str
    ) -> None:
        logger.warning("Law catalog error: %s", error)
        text, keyboard = ui.empty_law_menu(self.settings.bot_brand_name, error)
        await self._edit_or_send(chat_id, message_id, text, keyboard)

    async def _answer_question(
        self,
        *,
        chat_id: int,
        user_id: int,
        user: dict[str, Any],
        update_id: int | None,
        question: str,
        law: LawOption,
        mode: AnswerMode,
    ) -> None:
        logger.info(
            "Routing legal question chat_id=%s user_id=%s law_id=%s mode=%s chars=%s",
            chat_id,
            user_id,
            law.id,
            mode.value,
            len(question),
        )
        status = await self.telegram.send_message(
            chat_id, ui.processing_message(law, mode)
        )
        status_message_id = status.get("message_id")
        typing_task = asyncio.create_task(self._keep_typing(chat_id))
        context = TelegramContext(
            chat_id=chat_id,
            user_id=user_id,
            username=user.get("username"),
            first_name=user.get("first_name"),
            update_id=update_id,
        )
        try:
            answer = await self.gas.ask(mode, question, law, context)
        except GasError as exc:
            logger.warning(
                "GAS request failed chat_id=%s law_id=%s mode=%s error=%s",
                chat_id,
                law.id,
                mode.value,
                exc,
            )
            error_text = (
                "❌ <b>មិនអាចរៀបចំចម្លើយបាន</b>\n"
                f"{html.escape(str(exc))}\n\n"
                "សូមព្យាយាមម្ដងទៀត ឬប្ដូរច្បាប់/Mode។"
            )
            await self._edit_or_send(
                chat_id, status_message_id, error_text, ui.answer_keyboard()
            )
            return
        except Exception:
            logger.exception("Unexpected question handling error chat_id=%s", chat_id)
            await self._edit_or_send(
                chat_id,
                status_message_id,
                "❌ <b>មានបញ្ហាដែលមិនបានរំពឹងទុក</b>\nសូមសាកល្បងម្ដងទៀតបន្តិចក្រោយ។",
                ui.answer_keyboard(),
            )
            return
        finally:
            typing_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await typing_task

        chunks = ui.split_text(answer)
        disclaimer = "\n\n<i>⚠️ ព័ត៌មានជំនួយទូទៅ — មិនជំនួសការប្រឹក្សាផ្លូវច្បាប់វិជ្ជាជីវៈ។</i>"
        total = len(chunks)
        for index, chunk in enumerate(chunks):
            continuation = f" <i>({index + 1}/{total})</i>" if total > 1 else ""
            rendered = (
                ui.answer_header(law, mode)
                + continuation
                + ("\n" if continuation else "")
                + ui.escape_answer(chunk)
            )
            is_last = index == total - 1
            if is_last:
                rendered += disclaimer
            keyboard = ui.answer_keyboard() if is_last else None
            if index == 0:
                await self._edit_or_send(chat_id, status_message_id, rendered, keyboard)
            else:
                await self.telegram.send_message(chat_id, rendered, keyboard)

    async def _keep_typing(self, chat_id: int) -> None:
        while True:
            with contextlib.suppress(TelegramApiError):
                await self.telegram.send_chat_action(chat_id)
            await asyncio.sleep(4)

    async def _edit_or_send(
        self,
        chat_id: int,
        message_id: int | None,
        text: str,
        keyboard: dict[str, Any] | None = None,
    ) -> None:
        if isinstance(message_id, int):
            try:
                await self.telegram.edit_message(chat_id, message_id, text, keyboard)
                return
            except TelegramApiError as exc:
                if "message is not modified" in str(exc).lower():
                    return
                logger.info("Could not edit Telegram message; sending a new one")
        await self.telegram.send_message(chat_id, text, keyboard)
