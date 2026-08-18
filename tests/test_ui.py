from app.state import AnswerMode
from app.ui import main_menu, split_text


def test_menu_has_both_modes() -> None:
    text, keyboard = main_menu("នីតិ AI", AnswerMode.LITERAL)
    assert "ន័យត្រង់" in text
    assert "បែបអធិប្បាយ" in text
    callbacks = [
        button["callback_data"] for row in keyboard["inline_keyboard"] for button in row
    ]
    assert "mode:literal" in callbacks
    assert "mode:explain" in callbacks


def test_split_text_preserves_content() -> None:
    original = "ក" * 40 + "\n\n" + "ខ" * 40
    chunks = split_text(original, limit=50)
    assert len(chunks) == 2
    assert "".join(chunks) == original.replace("\n\n", "")
    assert all(len(chunk) <= 50 for chunk in chunks)
