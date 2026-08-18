from __future__ import annotations

import html
import math

from app.models import LawOption
from app.state import AnswerMode

DIVIDER = "━━━━━━━━━━━━━━━━━━"


def mode_label(mode: AnswerMode) -> str:
    return "⚡ ន័យត្រង់" if mode is AnswerMode.LITERAL else "✦ បែបអធិប្បាយ"


def mode_short_description(mode: AnswerMode) -> str:
    if mode is AnswerMode.LITERAL:
        return "ចម្លើយខ្លី ច្បាស់ និងត្រង់តាមខ្លឹមសារច្បាប់"
    return "ចម្លើយពន្យល់បរិបទ ហេតុផល និងការអនុវត្ត"


def law_menu(
    brand: str,
    laws: list[LawOption],
    page: int = 0,
    page_size: int = 8,
    current_law_id: str | None = None,
) -> tuple[str, dict]:
    total = len(laws)
    total_pages = max(1, math.ceil(total / page_size))
    page = min(max(0, page), total_pages - 1)
    start = page * page_size
    page_laws = laws[start : start + page_size]

    current = next((law for law in laws if law.id == current_law_id), None)
    current_text = (
        f"\n<b>បានជ្រើសបច្ចុប្បន្ន៖</b> {html.escape(current.title)}" if current else ""
    )
    text = (
        f"⚖️ <b>{html.escape(brand)} • LEGAL LIBRARY</b>\n"
        f"{DIVIDER}\n"
        "<b>ជំហានទី ១/៣ — ជ្រើសរើសច្បាប់</b>\n\n"
        "សូមជ្រើសច្បាប់ដែលអ្នកចង់សួរ។ ប្រព័ន្ធនឹងកំណត់ការស្វែងរក "
        "ទៅលើច្បាប់នោះ ដើម្បីផ្ដល់ចម្លើយឱ្យកាន់តែច្បាស់ និងត្រឹមត្រូវ។\n\n"
        f"📚 មានច្បាប់សកម្ម <b>{total}</b> • ទំព័រ <b>{page + 1}/{total_pages}</b>"
        f"{current_text}"
    )

    rows: list[list[dict[str, str]]] = [
        [{"text": law.button_text, "callback_data": f"law:{law.id}"}]
        for law in page_laws
    ]

    if total_pages > 1:
        navigation: list[dict[str, str]] = []
        if page > 0:
            navigation.append(
                {"text": "‹ មុន", "callback_data": f"laws:page:{page - 1}"}
            )
        navigation.append(
            {"text": f"{page + 1}/{total_pages}", "callback_data": "noop"}
        )
        if page < total_pages - 1:
            navigation.append(
                {"text": "បន្ទាប់ ›", "callback_data": f"laws:page:{page + 1}"}
            )
        rows.append(navigation)

    rows.append(
        [
            {"text": "↻ ធ្វើបច្ចុប្បន្នភាព", "callback_data": "catalog:refresh"},
            {"text": "🛡️ ជំនួយ", "callback_data": "help"},
        ]
    )
    return text, {"inline_keyboard": rows}


def empty_law_menu(brand: str, error: str | None = None) -> tuple[str, dict]:
    detail = f"\n\n<code>{html.escape(error)}</code>" if error else ""
    text = (
        f"⚖️ <b>{html.escape(brand)} • LEGAL LIBRARY</b>\n"
        f"{DIVIDER}\n"
        "មិនទាន់មានបញ្ជីច្បាប់សកម្ម ឬមិនអាចទាញបញ្ជីពី LAW_CATALOG បានទេ។"
        f"{detail}"
    )
    return text, {
        "inline_keyboard": [
            [{"text": "↻ សាកល្បងម្ដងទៀត", "callback_data": "catalog:refresh"}],
            [{"text": "🛡️ ជំនួយ", "callback_data": "help"}],
        ]
    }


def mode_menu(
    brand: str, law: LawOption, current_mode: AnswerMode | None = None
) -> tuple[str, dict]:
    current = (
        f"\n\n<b>Mode បច្ចុប្បន្ន៖</b> {mode_label(current_mode)}" if current_mode else ""
    )
    text = (
        f"⚖️ <b>{html.escape(brand)} • ANSWER MODE</b>\n"
        f"{DIVIDER}\n"
        "<b>ជំហានទី ២/៣ — ជ្រើសរបៀបឆ្លើយ</b>\n\n"
        f"📘 <b>ច្បាប់៖</b> {html.escape(law.title)}\n\n"
        "<b>⚡ ន័យត្រង់</b>\n"
        "ខ្លី ច្បាស់ និងត្រង់តាមខ្លឹមសារច្បាប់។\n\n"
        "<b>✦ បែបអធិប្បាយ</b>\n"
        "ពន្យល់បរិបទ ហេតុផល និងការអនុវត្តឱ្យបានទូលំទូលាយ។"
        f"{current}"
    )
    return text, {
        "inline_keyboard": [
            [{"text": "⚡ សំណួរ–ចម្លើយ ន័យត្រង់", "callback_data": "mode:literal"}],
            [{"text": "✦ សំណួរ–ចម្លើយ បែបអធិប្បាយ", "callback_data": "mode:explain"}],
            [
                {"text": "← ប្ដូរច្បាប់", "callback_data": "menu"},
                {"text": "🛡️ ជំនួយ", "callback_data": "help"},
            ],
        ]
    }


def mode_selected(brand: str, law: LawOption, mode: AnswerMode) -> tuple[str, dict]:
    example = (
        "ឧទាហរណ៍៖ តើមាត្រានេះកំណត់អ្វីខ្លះ?"
        if mode is AnswerMode.LITERAL
        else "ឧទាហរណ៍៖ សូមពន្យល់លក្ខខណ្ឌ និងផលវិបាកតាមច្បាប់នេះ។"
    )
    other = AnswerMode.EXPLAIN if mode is AnswerMode.LITERAL else AnswerMode.LITERAL
    text = (
        f"✅ <b>{html.escape(brand)} • READY</b>\n"
        f"{DIVIDER}\n"
        "<b>ជំហានទី ៣/៣ — ផ្ញើសំណួរ</b>\n\n"
        f"📘 <b>ច្បាប់៖</b> {html.escape(law.title)}\n"
        f"🎯 <b>Mode៖</b> {mode_label(mode)}\n\n"
        f"{mode_short_description(mode)}។\n\n"
        "ឥឡូវនេះ សូមវាយសំណួររបស់អ្នកក្នុងសារតែមួយ។\n"
        f"<i>{html.escape(example)}</i>"
    )
    return text, {
        "inline_keyboard": [
            [
                {
                    "text": f"ប្ដូរទៅ {mode_label(other)}",
                    "callback_data": f"mode:{other.value}",
                }
            ],
            [
                {"text": "📘 ប្ដូរច្បាប់", "callback_data": "menu"},
                {"text": "🛡️ ជំនួយ", "callback_data": "help"},
            ],
        ]
    }


def help_message(brand: str) -> tuple[str, dict]:
    text = (
        f"🛡️ <b>របៀបប្រើ {html.escape(brand)}</b>\n"
        f"{DIVIDER}\n"
        "<b>១.</b> ជ្រើសច្បាប់ពីបណ្ណាល័យច្បាប់។\n"
        "<b>២.</b> ជ្រើស «ន័យត្រង់» ឬ «បែបអធិប្បាយ»។\n"
        "<b>៣.</b> ផ្ញើសំណួរមួយឱ្យបានច្បាស់ក្នុងសារតែមួយ។\n"
        "<b>៤.</b> ច្បាប់ និង Mode នឹងត្រូវរក្សាទុក រហូតដល់អ្នកប្ដូរ។\n\n"
        "<b>ពាក្យបញ្ជា</b>\n"
        "/start — បើកបណ្ណាល័យច្បាប់\n"
        "/law — ប្ដូរច្បាប់\n"
        "/mode — ប្ដូររបៀបឆ្លើយ\n"
        "/menu — បើក Menu មេ\n"
        "/help — បង្ហាញជំនួយ\n\n"
        "⚠️ <i>ចម្លើយគឺជាព័ត៌មានជំនួយសម្រាប់ការស្រាវជ្រាវទូទៅ "
        "និងមិនជំនួសការប្រឹក្សាពីមេធាវី ឬស្ថាប័នមានសមត្ថកិច្ចឡើយ។</i>"
    )
    return text, {
        "inline_keyboard": [[{"text": "← ត្រឡប់ទៅបញ្ជីច្បាប់", "callback_data": "menu"}]]
    }


def processing_message(law: LawOption, mode: AnswerMode) -> str:
    return (
        "⏳ <b>កំពុងរៀបចំចម្លើយ</b>\n"
        f"📘 {html.escape(law.title)}\n"
        f"🎯 {mode_label(mode)}\n"
        "<i>សូមរង់ចាំបន្តិច…</i>"
    )


def answer_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "➕ សួរសំណួរបន្ត", "callback_data": "ask:again"}],
            [
                {"text": "🎯 ប្ដូរ Mode", "callback_data": "mode:menu"},
                {"text": "📘 ប្ដូរច្បាប់", "callback_data": "menu"},
            ],
            [{"text": "🛡️ ជំនួយ", "callback_data": "help"}],
        ]
    }


def answer_header(law: LawOption, mode: AnswerMode) -> str:
    return (
        f"{mode_label(mode)} • <b>ចម្លើយ</b>\n"
        f"📘 <i>{html.escape(law.title)}</i>\n{DIVIDER}\n"
    )


def escape_answer(text: str) -> str:
    return html.escape(text.strip(), quote=False)


def split_text(text: str, limit: int = 3300) -> list[str]:
    """Split long answers at paragraph/line/space boundaries."""
    text = text.strip()
    if not text:
        return [""]
    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        window = remaining[: limit + 1]
        cut = max(window.rfind("\n\n"), window.rfind("\n"), window.rfind(" "))
        if cut < limit // 2:
            cut = limit
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks
