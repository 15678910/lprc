# -*- coding: utf-8 -*-
"""판결문 본문 표지(tags) 시험 — 가짜 응답, 임시 폴더만 쓴다."""
import json

import pytest

import law_api
import prec_watch

ITEM = {"판례일련번호": "616245", "사건번호": "2023두54914", "사건명": "부당해고구제재심판정취소",
        "법원명": "대법원", "선고일자": "2026.01.29", "판결유형": "판결"}
BODY_SECRET = "원문전용문장ZXQ"


def _terms(tmp_path, body=("직장 내 괴롭힘", "불법파견")):
    p = tmp_path / "terms_test.json"
    p.write_text(json.dumps({"issues": [{"id": "a", "body": list(body[:1])},
                                        {"id": "b", "body": list(body[1:])}]}, ensure_ascii=False),
                 encoding="utf-8")
    return str(p)


def _setup(tmp_path, monkeypatch, terms=None):
    out = tmp_path / "out"
    monkeypatch.setenv("LAW_OC", "secret123")
    monkeypatch.setattr(prec_watch, "OUT", str(out))
    monkeypatch.setattr(prec_watch, "TERMS", terms or _terms(tmp_path))
    monkeypatch.setattr(prec_watch, "VARIANTS", {"근로기준법": ["근로기준법"]})
    return out


def _fake(calls, fail=False, body="본문 중 직장  내\n괴롭힘 이 인정되었다. " + BODY_SECRET):
    def fake(url, oc):
        if "lawSearch" in url:
            if "page=1" in url:
                return {"PrecSearch": {"totalCnt": "1", "prec": [dict(ITEM)]}}
            return {"PrecSearch": {"totalCnt": "1", "prec": []}}
        calls.append(url)
        if fail:
            raise RuntimeError("요청 실패")
        return {"PrecService": {"판시사항": "쟁점", "판결요지": "요지", "참조조문": "조문", "판례내용": body}}
    return fake


def _read_d(out):
    return json.loads((out / "d" / "45.json").read_text(encoding="utf-8"))["616245"]


def test_body_tags_whitespace_original_form_and_empty():
    ph = ["직장 내 괴롭힘", "불법파견"]
    assert prec_watch.body_tags("직장내\n괴롭힘<br/>이 있다", ph) == ["직장 내 괴롭힘"]
    assert prec_watch.body_tags("불법 파견 및 직장 내 괴롭힘", ph) == ["불법파견", "직장 내 괴롭힘"]
    assert prec_watch.body_tags("아무 말", ph) == []


def test_body_phrases_sorted_unique_and_errors(tmp_path):
    p = tmp_path / "t.json"
    p.write_text(json.dumps({"issues": [{"body": ["나", "가"]}, {"body": ["가"]}, {}]}), encoding="utf-8")
    assert prec_watch.body_phrases(str(p)) == ["가", "나"]
    assert len(prec_watch.tags_version(["가", "나"])) == 8
    assert prec_watch.tags_version(["가"]) != prec_watch.tags_version(["가", "나"])
    with pytest.raises(RuntimeError):
        prec_watch.body_phrases(str(tmp_path / "none.json"))
    p.write_text(json.dumps({"issues": [{"id": "x"}]}), encoding="utf-8")
    with pytest.raises(RuntimeError):
        prec_watch.body_phrases(str(p))


def test_first_run_tags_in_d_and_index_no_body_text(tmp_path, monkeypatch):
    out = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(prec_watch, "fetch_json", _fake([]))
    assert prec_watch.main([]) == 0
    d = _read_d(out)
    assert d["tags"] == ["직장 내 괴롭힘"] and d["tv"] == prec_watch.tags_version(["불법파견", "직장 내 괴롭힘"])
    idx = json.loads((out / "index.json").read_text(encoding="utf-8"))
    assert idx["records"][0]["tags"] == ["직장 내 괴롭힘"]
    blob = "".join(p.read_text(encoding="utf-8") for p in out.rglob("*.json"))
    assert BODY_SECRET not in blob and "판례내용" not in blob


def test_empty_tags_in_d_but_not_in_index(tmp_path, monkeypatch):
    out = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(prec_watch, "fetch_json", _fake([], body="해당 없음"))
    assert prec_watch.main([]) == 0
    assert _read_d(out)["tags"] == []
    idx = json.loads((out / "index.json").read_text(encoding="utf-8"))
    assert "tags" not in idx["records"][0]


def test_rerun_same_tv_makes_no_detail_requests(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(prec_watch, "fetch_json", _fake([]))
    assert prec_watch.main([]) == 0
    calls = []
    monkeypatch.setattr(prec_watch, "fetch_json", _fake(calls))
    assert prec_watch.main([]) == 0
    assert calls == []


def test_changed_phrases_recheck_updates_tags(tmp_path, monkeypatch):
    out = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(prec_watch, "fetch_json", _fake([], body="직장 내 괴롭힘 그리고 불법파견"))
    assert prec_watch.main([]) == 0
    assert _read_d(out)["tags"] == ["불법파견", "직장 내 괴롭힘"]
    monkeypatch.setattr(prec_watch, "TERMS", _terms(tmp_path, ("직장 내 괴롭힘", "그리고")))
    calls = []
    monkeypatch.setattr(prec_watch, "fetch_json", _fake(calls, body="직장 내 괴롭힘 그리고 불법파견"))
    assert prec_watch.main([]) == 0
    assert len(calls) == 1
    assert _read_d(out)["tags"] == ["그리고", "직장 내 괴롭힘"]


def test_recheck_failure_keeps_old_detail_and_retries_next_run(tmp_path, monkeypatch, capsys):
    out = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(prec_watch, "fetch_json", _fake([]))
    assert prec_watch.main([]) == 0
    before = _read_d(out)
    monkeypatch.setattr(prec_watch, "TERMS", _terms(tmp_path, ("직장 내 괴롭힘", "그리고")))
    monkeypatch.setattr(prec_watch, "fetch_json", _fake([], fail=True))
    assert prec_watch.main([]) == 0
    assert _read_d(out) == before  # d 조각에서 사라지지 않고 그대로
    assert "다시 확인 실패 1건" in capsys.readouterr().out
    calls = []
    monkeypatch.setattr(prec_watch, "fetch_json", _fake(calls))
    assert prec_watch.main([]) == 0
    assert len(calls) == 1  # 다음 실행 때 다시 확인


def test_auth_failure_during_recheck_aborts(tmp_path, monkeypatch):
    out = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(prec_watch, "fetch_json", _fake([]))
    assert prec_watch.main([]) == 0
    before = (out / "d" / "45.json").read_text(encoding="utf-8")
    monkeypatch.setattr(prec_watch, "TERMS", _terms(tmp_path, ("직장 내 괴롭힘", "그리고")))
    base = _fake([])

    def fake(url, oc):
        if "lawService" in url:
            raise law_api.LawAuthError("인증 실패")
        return base(url, oc)

    monkeypatch.setattr(prec_watch, "fetch_json", fake)
    assert prec_watch.main([]) == 1
    assert (out / "d" / "45.json").read_text(encoding="utf-8") == before


def test_missing_terms_json_exits_1(tmp_path, monkeypatch):
    out = _setup(tmp_path, monkeypatch, terms=str(tmp_path / "none.json"))
    calls = []
    monkeypatch.setattr(prec_watch, "fetch_json", _fake(calls))
    assert prec_watch.main([]) == 1
    assert calls == [] and not out.exists()
