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
