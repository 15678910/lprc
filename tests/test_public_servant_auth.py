# -*- coding: utf-8 -*-
import ssl
import urllib.request

import pytest

import law_api
import public_servant


class _Resp:
    def read(self):
        return b'{"LawSearch": {"law": []}}'

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_law_uses_verified_tls(monkeypatch):
    """_law 는 인증서·호스트명 검증을 끈 컨텍스트를 쓰면 안 된다(키가 URL 에 실린다)."""
    monkeypatch.setenv("LAW_OC", "abc123")
    seen = {}

    class FakeOpener:
        def open(self, req, timeout=None):
            return _Resp()

    def fake_build_opener(*handlers):
        for h in handlers:
            if isinstance(h, urllib.request.HTTPSHandler):
                seen["ctx"] = h._context
        return FakeOpener()

    monkeypatch.setattr(urllib.request, "build_opener", fake_build_opener)
    public_servant._law("lawSearch", target="eflaw")
    ctx = seen["ctx"]
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True


def _boom(*a, **k):
    raise law_api.LawAuthError("사용자 정보 검증에 실패하였습니다.")


def test_allowance_does_not_swallow_auth_error(monkeypatch):
    monkeypatch.setattr(public_servant, "_law", _boom)
    with pytest.raises(law_api.LawAuthError):
        public_servant.allowance()


def test_allowance_does_not_swallow_missing_key(monkeypatch):
    monkeypatch.delenv("LAW_OC", raising=False)
    with pytest.raises(RuntimeError):
        public_servant.allowance()


def test_allowance_year_loop_does_not_swallow_auth_error(monkeypatch):
    calls = {"n": 0}

    def fake_law(path, **p):
        calls["n"] += 1
        if path == "lawSearch":
            return {"LawSearch": {"law": [{"법령명한글": public_servant.LAW_NAME,
                                           "시행일자": "20200101", "법령일련번호": "1"}]}}
        raise law_api.LawAuthError("거부")

    monkeypatch.setattr(public_servant, "_law", fake_law)
    with pytest.raises(law_api.LawAuthError):
        public_servant.allowance()


def test_main_keeps_existing_file_on_auth_error(monkeypatch, tmp_path):
    out = tmp_path / "public_servant.json"
    out.write_text("OLD", encoding="utf-8")
    monkeypatch.setattr(public_servant, "OUTPUT_FILE", str(out))
    monkeypatch.setattr(public_servant, "PAY_FILE", str(tmp_path / "pay.json"))
    monkeypatch.setattr(public_servant, "pay_tables", lambda y: [{"x": 1}])
    monkeypatch.setattr(public_servant, "general_grade", lambda t: None)
    monkeypatch.setattr(public_servant.time, "sleep", lambda s: None)
    monkeypatch.setattr(public_servant, "allowance", _boom)
    assert public_servant.main() == 1
    assert out.read_text(encoding="utf-8") == "OLD"
