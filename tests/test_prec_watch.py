# -*- coding: utf-8 -*-
import gzip
import json
import os

import pytest

import law_api
import prec_watch

ITEM = {"판례일련번호": "616245", "사건번호": "2023두54914", "사건명": "부당해고구제재심판정취소",
        "법원명": "대법원", "선고일자": "2026.01.29", "판결유형": "판결",
        "판례상세링크": "/DRF/lawService.do?OC=secret123&target=prec&ID=616245"}
DETAIL = {"판시사항": "<br/> [1] 근로자 판단 기준", "판결요지": "", "참조조문": "근로기준법 제2조"}


def test_record_is_allowlisted():
    r = prec_watch.to_record(ITEM, DETAIL, ["근로기준법"])
    assert set(r) == {"id", "no", "name", "court", "date", "type", "issue", "gist", "refs", "laws", "tags", "tv"}
    assert "secret123" not in json.dumps(r, ensure_ascii=False)
    assert "판례상세링크" not in json.dumps(r, ensure_ascii=False)


def test_strip_html():
    assert prec_watch.strip_html("<br/> [1] 기준<br/>") == "[1] 기준"


def test_missing_detail_keeps_listing_fields():
    r = prec_watch.to_record(ITEM, None, ["근로기준법"])
    assert r["no"] == "2023두54914" and r["issue"] == "" and r["gist"] == ""


def test_assert_no_key_raises():
    with pytest.raises(RuntimeError):
        prec_watch.assert_no_key('{"x":"OC=secret123"}', "secret123")


def test_assert_no_key_catches_pattern_and_link_without_key():
    with pytest.raises(RuntimeError):
        prec_watch.assert_no_key('{"x":"OC=zzz"}', "secret123")
    with pytest.raises(RuntimeError):
        prec_watch.assert_no_key('{"판례상세링크":"/x"}', "secret123")
    prec_watch.assert_no_key('{"x":"정상"}', "secret123")


def test_guard_shrink_refuses_big_drop():
    with pytest.raises(RuntimeError):
        prec_watch.guard_shrink(800, 1000)
    prec_watch.guard_shrink(950, 1000)
    prec_watch.guard_shrink(10, 0)


def test_write_if_changed_is_idempotent(tmp_path):
    p = str(tmp_path / "a.json")
    assert prec_watch.write_if_changed(p, {"a": 1}) is True
    assert prec_watch.write_if_changed(p, {"a": 1}) is False


def test_build_outputs_splits_shards():
    idx, shards = prec_watch.build_outputs([prec_watch.to_record(ITEM, DETAIL, ["근로기준법"])])
    assert idx["records"][0]["id"] == 616245
    assert "616245" in shards["45"]


def test_shard_of():
    assert prec_watch.shard_of(616245) == "45"
    assert prec_watch.shard_of(7) == "07"


def test_failed_detail_not_in_shard():
    r = prec_watch.to_record(ITEM, None, ["근로기준법"])
    idx, shards = prec_watch.build_outputs([r], failed={616245})
    assert idx["records"][0]["id"] == 616245
    assert shards == {}


def test_gist_in_index_zero_drops_gist_from_text(monkeypatch):
    d = dict(DETAIL, **{"판결요지": "요지본문"})
    monkeypatch.setattr(prec_watch, "GIST_IN_INDEX", 0)
    idx, shards = prec_watch.build_outputs([prec_watch.to_record(ITEM, d, ["근로기준법"])])
    assert "요지본문" not in idx["records"][0]["text"]
    monkeypatch.setattr(prec_watch, "GIST_IN_INDEX", 300)
    idx, _ = prec_watch.build_outputs([prec_watch.to_record(ITEM, d, ["근로기준법"])])
    assert "요지본문" in idx["records"][0]["text"]


def test_http_uses_verified_https_only():
    with pytest.raises(RuntimeError):
        prec_watch.fetch_json("http://www.law.go.kr/x", "k")


def test_fetch_auth_error_not_retried(monkeypatch):
    calls = []

    def fake(url):
        calls.append(url)
        return json.dumps({"result": "사용자 정보 검증에 실패하였습니다.", "msg": "x"}).encode()

    monkeypatch.setattr(prec_watch, "_open", fake)
    monkeypatch.setattr(prec_watch.time, "sleep", lambda s: None)
    with pytest.raises(law_api.LawAuthError):
        prec_watch.fetch_json("https://www.law.go.kr/DRF/lawSearch.do?OC=k", "k")
    assert len(calls) == 1


def test_main_auth_failure_exits_1_and_preserves_files(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LAW_OC", "secret123")
    monkeypatch.setattr(prec_watch, "OUT", str(tmp_path))
    (tmp_path / "meta.json").write_text("OLD", encoding="utf-8")

    def boom(url, oc):
        raise law_api.LawAuthError("실패 OC=secret123")

    monkeypatch.setattr(prec_watch, "fetch_json", boom)
    assert prec_watch.main([]) == 1
    assert (tmp_path / "meta.json").read_text(encoding="utf-8") == "OLD"
    out = capsys.readouterr()
    assert "secret123" not in out.out + out.err


def test_main_missing_key_exits_1(monkeypatch):
    monkeypatch.delenv("LAW_OC", raising=False)
    assert prec_watch.main([]) == 1


def test_main_end_to_end_with_fake_api(tmp_path, monkeypatch):
    monkeypatch.setenv("LAW_OC", "secret123")
    monkeypatch.setattr(prec_watch, "OUT", str(tmp_path))
    monkeypatch.setattr(prec_watch, "LAWS", ["근로기준법"])
    monkeypatch.setattr(prec_watch, "VARIANTS", {"근로기준법": ["근로기준법"]})

    def fake(url, oc):
        if "lawSearch" in url:
            if "page=1" in url:
                return {"PrecSearch": {"totalCnt": "1", "prec": [dict(ITEM)]}}
            return {"PrecSearch": {"totalCnt": "1", "prec": []}}
        return {"PrecService": {"판시사항": "쟁점<br/>", "판결요지": "요지", "참조조문": "조문"}}

    monkeypatch.setattr(prec_watch, "fetch_json", fake)
    assert prec_watch.main([]) == 0
    idx = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    assert idx["records"][0]["id"] == 616245
    assert (tmp_path / "d" / "45.json").exists()
    meta = json.loads((tmp_path / "meta.json").read_text(encoding="utf-8"))
    assert meta["total"] == 1 and meta["by_law"]["근로기준법"] == 1
    blob = "".join(p.read_text(encoding="utf-8") for p in tmp_path.rglob("*.json"))
    assert "secret123" not in blob and "OC=" not in blob and "판례상세링크" not in blob
    assert len(gzip.compress((tmp_path / "index.json").read_bytes())) < 2_000_000
    # 재실행: 쓰기 없음
    before = os.path.getmtime(tmp_path / "index.json")
    assert prec_watch.main([]) == 0
    assert os.path.getmtime(tmp_path / "index.json") == before


def _save_once(tmp_path, **kw):
    rec_items = {616245: dict(ITEM)}
    return prec_watch.save(str(tmp_path), "secret123", rec_items, {616245: {"근로기준법"}},
                           {"616245": DETAIL}, set(), 0, **kw)


def test_save_force_meta_rewrites_meta_when_content_same(tmp_path):
    _save_once(tmp_path)
    mp = tmp_path / "meta.json"
    mp.write_text(json.dumps({"generated_at": "2000-01-01T00:00:00Z", "total": 1,
                              "by_law": {"근로기준법": 1}}), encoding="utf-8")
    _save_once(tmp_path)  # 기본값: 내용이 같으면 건드리지 않는다
    assert json.loads(mp.read_text(encoding="utf-8"))["generated_at"] == "2000-01-01T00:00:00Z"
    _save_once(tmp_path, force_meta=True)
    meta = json.loads(mp.read_text(encoding="utf-8"))
    assert meta["generated_at"] != "2000-01-01T00:00:00Z" and meta["total"] == 1


def test_main_refreshes_meta_even_without_new_cases(tmp_path, monkeypatch):
    monkeypatch.setenv("LAW_OC", "secret123")
    monkeypatch.setattr(prec_watch, "OUT", str(tmp_path))
    monkeypatch.setattr(prec_watch, "VARIANTS", {"근로기준법": ["근로기준법"]})

    def fake(url, oc):
        if "lawSearch" in url:
            if "page=1" in url:
                return {"PrecSearch": {"totalCnt": "1", "prec": [dict(ITEM)]}}
            return {"PrecSearch": {"totalCnt": "1", "prec": []}}
        return {"PrecService": {"판시사항": "쟁점<br/>", "판결요지": "요지", "참조조문": "조문"}}

    monkeypatch.setattr(prec_watch, "fetch_json", fake)
    assert prec_watch.main([]) == 0
    mp = tmp_path / "meta.json"
    mp.write_text(json.dumps({"generated_at": "2000-01-01T00:00:00Z", "total": 1,
                              "by_law": {"근로기준법": 1}}), encoding="utf-8")
    assert prec_watch.main([]) == 0
    meta = json.loads(mp.read_text(encoding="utf-8"))
    assert meta["generated_at"] != "2000-01-01T00:00:00Z" and meta["total"] == 1
