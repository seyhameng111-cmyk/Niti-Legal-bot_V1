from __future__ import annotations

import html

from app.state import AnswerMode

DIVIDER = "━━━━━━━━━━━━━━━━━━"


def mode_label(mode: AnswerMode) -> str:
    return "⚡ ន័យត្រង់" if mode is AnswerMode.LITERAL else "✦ បែបអធិប្បាយ"


def mode_short_description(mode: AnswerMode) -> str:
    if mode is AnswerMode.LITERAL:
        return "ចម្លើយខ្លី ច្បាស់ និងត្រង់តាមខ្លឹមសារច្បាប់"
    return "ចម្លើយពន្យល់បរិបទ ហេតុផល និងការអនុវត្ត"


def main_menu(brand: str, current_mode: AnswerMode | None = None) -> tuple[str, dict]:
    current = ""
    if current_mode:
        current = f"\n\n<b>Mode បច្ចុប្បន្ន៖</b> {mode_label(current_mode)}"
    text = (
        f"⚖️ <b>{html.escape(brand)} • LEGAL INTELLIGENCE</b>\n"
        f"{DIVIDER}\n"
        "សូមជ្រើសរើសរបៀបឆ្លើយតបដែលសមនឹងតម្រូវការរបស់អ្នក៖\n\n"
        "<b>⚡ ន័យត្រង់</b>\n"
        "ចម្លើយខ្លី ច្បាស់ និងផ្អែកត្រង់លើខ្លឹមសារច្បាប់។\n\n"
        "<b>✦ បែបអធិប្បាយ</b>\n"
        "ពន្យល់បរិបទ ហេតុផល និងការអនុវត្តឱ្យបានទូលំទូលាយ។"
        f"{current}\n\n"
        "<i>ជ្រើសរើស Mode មួយ ហើយផ្ញើសំណួររបស់អ្នក។</i>"
    )
    keyboard = {
        "inline_keyboard": [
            [{"text": "⚡ សំណួរ–ចម្លើយ ន័យត្រង់", "callback_data": "mode:literal"}],
            [{"text": "✦ សំណួរ–ចម្លើយ បែបអធិប្បាយ", "callback_data": "mode:explain"}],
            [{"text": "🛡️ របៀបប្រើ និងការកត់សម្គាល់", "callback_data": "help"}],
        ]
    }
    return text, keyboard


def mode_selected(brand: str, mode: AnswerMode) -> tuple[str, dict]:
    example = (
        "ឧទាហរណ៍៖ តើកិច្ចសន្យាមានសុពលភាពនៅពេលណា?"
        if mode is AnswerMode.LITERAL
        else "ឧទាហរណ៍៖ សូមពន្យល់លក្ខខណ្ឌ និងផលវិបាកនៃការរំលោភកិច្ចសន្យា។"
    )
    other = AnswerMode.EXPLAIN if mode is AnswerMode.LITERAL else AnswerMode.LITERAL
    text = (
        f"✅ <b>{html.escape(brand)} បានកំណត់ Mode រួចរាល់</b>\n"
        f"{DIVIDER}\n"
        f"<b>{mode_label(mode)}</b>\n"
        f"{mode_short_description(mode)}។\n\n"
        "ឥឡូវនេះ សូមវាយសំណួរច្បាប់របស់អ្នកផ្ញើមកខ្ញុំ។\n"
        f"<i>{html.escape(example)}</i>"
    )
    keyboard = {
        "inline_keyboard": [
            [
                {
                    "text": f"ប្ដូរទៅ {mode_label(other)}",
                    "callback_data": f"mode:{other.value}",
                }
            ],
            [
                {"text": "🏠 Menu មេ", "callback_data": "menu"},
                {"text": "🛡️ ជំនួយ", "callback_data": "help"},
            ],
        ]
    }
    return text, keyboard


def help_message(brand: str) -> tuple[str, dict]:
    text = (
        f"🛡️ <b>របៀបប្រើ {html.escape(brand)}</b>\n"
        f"{DIVIDER}\n"
        "<b>១.</b> ជ្រើស «ន័យត្រង់» ឬ «បែបអធិប្បាយ»។\n"
        "<b>២.</b> ផ្ញើសំណួរមួយឱ្យបានច្បាស់ក្នុងសារតែមួយ។\n"
        "<b>៣.</b> Mode នឹងត្រូវរក្សាទុក រហូតដល់អ្នកប្ដូរវា។\n\n"
        "<b>ពាក្យបញ្ជា</b>\n"
        "/start — ចាប់ផ្ដើមសារជាថ្មី\n"
        "/menu — បើក Menu ជ្រើសរើស\n"
        "/mode — ប្ដូររបៀបឆ្លើយ\n"
        "/help — បង្ហាញជំនួយ\n\n"
        "⚠️ <i>ចម្លើយគឺជាព័ត៌មានជំនួយសម្រាប់ការស្រាវជ្រាវទូទៅ "
        "និងមិនជំនួសការប្រឹក្សាពីមេធាវី ឬស្ថាប័នមានសមត្ថកិច្ចឡើយ។</i>"
    )
    return text, {
        "inline_keyboard": [[{"text": "← ត្រឡប់ទៅ Menu", "callback_data": "menu"}]]
    }


def processing_message(mode: AnswerMode) -> str:
    return f"⏳ <b>កំពុងរៀបចំចម្លើយ</b>\nMode៖ {mode_label(mode)}\n<i>សូមរង់ចាំបន្តិច…</i>"


def answer_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "➕ សួរសំណួរបន្ត", "callback_data": "ask:again"}],
            [
                {"text": "🔄 ប្ដូរ Mode", "callback_data": "menu"},
                {"text": "🛡️ ជំនួយ", "callback_data": "help"},
            ],
        ]
    }


def answer_header(mode: AnswerMode) -> str:
    return f"{mode_label(mode)} • <b>ចម្លើយ</b>\n{DIVIDER}\n"


def escape_answer(text: str) -> str:
    return html.escape(text.strip(), quote=False)


def split_text(text: str, limit: int = 3400) -> list[str]:
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
