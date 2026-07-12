"""retry_api_error デコレータのテスト"""
import gspread
import pytest

from netaichi.helper import gss


class FakeResponse:
    def __init__(self, code: int):
        self._code = code

    def json(self):
        return {"error": {"code": self._code, "message": "", "status": ""}}


def api_error(code: int) -> gspread.exceptions.APIError:
    return gspread.exceptions.APIError(FakeResponse(code))


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(gss, "sleep", lambda _: None)


def test_503は再試行して成功したら値を返す():
    calls = []

    @gss.retry_api_error
    def func():
        calls.append(1)
        if len(calls) < 3:
            raise api_error(503)
        return "ok"

    assert func() == "ok"
    assert len(calls) == 3


def test_503が続いたら3回で諦めて例外を上げる():
    calls = []

    @gss.retry_api_error
    def func():
        calls.append(1)
        raise api_error(503)

    with pytest.raises(gspread.exceptions.APIError):
        func()
    assert len(calls) == 3


def test_4xxは再試行しない():
    calls = []

    @gss.retry_api_error
    def func():
        calls.append(1)
        raise api_error(404)

    with pytest.raises(gspread.exceptions.APIError):
        func()
    assert len(calls) == 1
