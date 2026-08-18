import httpx
import pytest

from app.gas_client import GasClient, GasError


def response(body: str, content_type: str = "application/json") -> httpx.Response:
    return httpx.Response(
        200,
        text=body,
        headers={"content-type": content_type},
        request=httpx.Request("POST", "https://example.com/exec"),
    )


def test_extracts_configured_nested_path() -> None:
    result = GasClient._extract_answer(
        response('{"data":{"result":{"text":"ចម្លើយ"}}}'),
        "data.result.text",
    )
    assert result == "ចម្លើយ"


def test_falls_back_to_common_answer_field() -> None:
    result = GasClient._extract_answer(response('{"answer":"OK"}'), "missing")
    assert result == "OK"


def test_accepts_plain_text() -> None:
    result = GasClient._extract_answer(
        response("Plain response", "text/plain; charset=utf-8"), "answer"
    )
    assert result == "Plain response"


def test_recognizes_gas_error_envelope() -> None:
    with pytest.raises(GasError, match="Unauthorized"):
        GasClient._extract_answer(
            response('{"ok":false,"error":"Unauthorized"}'), "answer"
        )


def test_rejects_html_permission_page() -> None:
    with pytest.raises(GasError, match="HTML"):
        GasClient._extract_answer(
            response("<!doctype html><html>Login</html>", "text/html"), "answer"
        )
