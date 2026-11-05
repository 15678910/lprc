# -*- coding: utf-8 -*-
import pytest

import law_api
import law_watch


def raise_auth_error(*a, **k):
    raise law_api.LawAuthError("검증 실패")


def test_law_oc_requires_env(monkeypatch):
    monkeypatch.delenv("LAW_OC", raising=False)
    with pytest.raises(RuntimeError):
        law_api.law_oc()


def test_check_auth_raises_on_verification_failure():
    with pytest.raises(law_api.LawAuthError):
        law_api.check_auth({"result": "사용자 정보 검증에 실패하였습니다.", "msg": "x"})


def test_check_auth_passes_normal_payload():
    data = {"LawSearch": {"totalCnt": "1"}}
    assert law_api.check_auth(data) is data


def test_redact_removes_key(monkeypatch):
    monkeypatch.setenv("LAW_OC", "abc123")
    assert "abc123" not in law_api.redact("url?OC=abc123&x=1")


def test_law_watch_exits_nonzero_on_auth_failure(monkeypatch, tmp_path):
    monkeypatch.setenv("LAW_OC", "abc123")
    monkeypatch.setattr(law_watch, "OUT", str(tmp_path / "law_watch.json"))
    monkeypatch.setattr(law_watch, "fetch_current", raise_auth_error)
    assert law_watch.main() == 1
    assert not (tmp_path / "law_watch.json").exists()


def test_redact_removes_encoded_key(monkeypatch):
    monkeypatch.setenv("LAW_OC", "abc+1/x")
    for form in ("abc+1/x", "abc%2B1%2Fx", "abc%2B1/x", "abc%2b1/x".replace("%2b", "%2B")):
        assert "abc" not in law_api.redact("u?OC=" + form + "&q=1"), form
    assert "abc" not in law_api.redact("err abc%2B1%2Fx tail")
    assert "abc" not in law_api.redact("err abc%2B1/x tail")


def test_redact_pattern_without_env_and_empty_key(monkeypatch):
    monkeypatch.delenv("LAW_OC", raising=False)
    assert law_api.redact("a b c") == "a b c"
    assert "zzz" not in law_api.redact("http://x?OC=zzz&a=1")


def _serve(handler_cls):
    import http.server
    import threading
    srv = http.server.HTTPServer(("127.0.0.1", 0), handler_cls)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def test_opener_does_not_follow_redirect():
    import http.server
    import urllib.error
    import urllib.request
    hits = []

    class Second(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"x")

        def log_message(self, *a):
            pass

    second = _serve(Second)
    target = "http://127.0.0.1:%d/leak?OC=secret" % second.server_address[1]

    class First(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(302)
            self.send_header("Location", target)
            self.end_headers()

        def log_message(self, *a):
            pass

    first = _serve(First)
    try:
        opener = law_api._build_opener()
        with pytest.raises(urllib.error.HTTPError):
            opener.open("http://127.0.0.1:%d/a?OC=secret" % first.server_address[1], timeout=5)
        assert hits == []
    finally:
        first.shutdown()
        second.shutdown()


def test_open_law_rejects_non_law_urls(monkeypatch):
    monkeypatch.setenv("LAW_OC", "topsecret9")
    for url in ("http://www.law.go.kr/DRF/x?OC=topsecret9",
                "https://evil.example/DRF/x?OC=topsecret9",
                "https://www.law.go.kr.evil.example/x?OC=topsecret9"):
        with pytest.raises(RuntimeError) as ei:
            law_api.open_law(url, {}, 1)
        assert "OC=" not in str(ei.value)
        assert "topsecret9" not in str(ei.value)


def test_law_watch_exits_nonzero_when_key_missing(monkeypatch, tmp_path):
    monkeypatch.delenv("LAW_OC", raising=False)
    monkeypatch.setattr(law_watch, "OUT", str(tmp_path / "law_watch.json"))
    assert law_watch.main() == 1
    assert not (tmp_path / "law_watch.json").exists()
