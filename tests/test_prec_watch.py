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
        prec_watch.fetch_json("http://www.law.go.kr/x")


def test_fetch_auth_error_not_retried(monkeypatch):
    calls = []

    def fake(url):
        calls.append(url)
        return json.dumps({"result": "사용자 정보 검증에 실패하였습니다.", "msg": "x"}).encode()

    monkeypatch.setattr(prec_watch, "_open", fake)
    monkeypatch.setattr(prec_watch.time, "sleep", lambda s: None)
    with pytest.raises(law_api.LawAuthError):
        prec_watch.fetch_json("https://www.law.go.kr/DRF/lawSearch.do?OC=k")
    assert len(calls) == 1


def test_main_auth_failure_exits_1_and_preserves_files(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LAW_OC", "secret123")
    monkeypatch.setattr(prec_watch, "OUT", str(tmp_path))
    (tmp_path / "meta.json").write_text("OLD", encoding="utf-8")

    def boom(url):
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

    def fake(url):
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

    def fake(url):
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


BLANK = dict(ITEM, 사건번호="", 법원명="", 선고일자="0001.01.01", 판결유형="")
BLANK_DETAIL = {"판시사항": "", "판결요지": "", "참조조문": "", "tags": [], "tv": "t1",
                "사건번호": "2023누39177", "법원명": "서울고등법원"}


def test_blank_list_item_takes_case_no_and_court_from_detail():
    """근로복지공단 산재판례: 목록에는 비어 있고 상세에만 있다. 선고일은 어디에도 없다."""
    r = prec_watch.to_record(BLANK, BLANK_DETAIL, ["근로기준법"])
    assert (r["no"], r["court"], r["date"]) == ("2023누39177", "서울고등법원", "")


def test_placeholder_date_is_never_published():
    assert prec_watch.clean_date("0001.01.01") == ""
    assert prec_watch.clean_date("00010101") == ""
    assert prec_watch.clean_date("") == ""
    assert prec_watch.clean_date("2026.01.29") == "2026.01.29"


def test_detail_meta_survives_the_next_run(tmp_path):
    """상세에서 얻은 사건번호는 조각에 남아, 다음 실행의 빈 목록 응답으로 사라지지 않는다."""
    r = prec_watch.to_record(BLANK, BLANK_DETAIL, ["근로기준법"])
    idx, shards = prec_watch.build_outputs([r])
    assert idx["records"][0]["no"] == "2023누39177"
    entry = shards[prec_watch.shard_of(r["id"])][str(r["id"])]
    assert entry["no"] == "2023누39177" and entry["court"] == "서울고등법원"
    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "00.json").write_text(json.dumps({str(r["id"]): entry}), encoding="utf-8")
    details, _ = prec_watch.load_existing(str(tmp_path))
    again = prec_watch.to_record(BLANK, details[str(r["id"])], ["근로기준법"])
    assert (again["no"], again["court"]) == ("2023누39177", "서울고등법원")


def test_normal_records_add_nothing_to_shards():
    r = prec_watch.to_record(ITEM, dict(DETAIL, 사건번호="x", 법원명="y"), ["근로기준법"])
    _, shards = prec_watch.build_outputs([r])
    assert "no" not in shards[prec_watch.shard_of(r["id"])][str(r["id"])]


def test_needs_recheck():
    assert prec_watch.needs_recheck(ITEM, {"tv": "old"}, "t1")
    assert not prec_watch.needs_recheck(ITEM, {"tv": "t1"}, "t1")
    assert prec_watch.needs_recheck(BLANK, {"tv": "t1"}, "t1")  # 상세 정보를 아직 안 받음
    assert not prec_watch.needs_recheck(BLANK, {"tv": "t1", "사건번호": ""}, "t1")  # 받았지만 비어 있음: 매주 묻지 않는다


def test_court_only_blank_survives_the_next_run(tmp_path):
    """사건번호는 있고 법원만 빈 목록 응답도, 상세의 법원을 잃지 않고 매주 다시 묻지도 않는다."""
    item = dict(ITEM, 법원명="")
    assert prec_watch.needs_recheck(item, {"tv": "t1"}, "t1")
    r = prec_watch.to_record(item, dict(DETAIL, 사건번호="x", 법원명="서울고등법원"), ["근로기준법"])
    _, shards = prec_watch.build_outputs([r])
    entry = shards[prec_watch.shard_of(r["id"])][str(r["id"])]
    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "00.json").write_text(json.dumps({str(r["id"]): entry}), encoding="utf-8")
    details, _ = prec_watch.load_existing(str(tmp_path))
    det = details[str(r["id"])]
    assert prec_watch.to_record(item, det, ["근로기준법"])["court"] == "서울고등법원"
    assert not prec_watch.needs_recheck(item, dict(det, tv="t1"), "t1")


def test_internal_flag_is_not_published():
    r = prec_watch.to_record(BLANK, BLANK_DETAIL, ["근로기준법"])
    assert r["meta_from_detail"]
    idx, shards = prec_watch.build_outputs([r])
    assert "meta_from_detail" not in idx["records"][0]
    assert "meta_from_detail" not in shards[prec_watch.shard_of(r["id"])][str(r["id"])]


def _rec(i, **kw):
    r = prec_watch.to_record(dict(ITEM, 판례일련번호=str(i)), DETAIL, ["근로기준법"])
    r.update(kw)
    return r


def test_same_judgment_listed_twice_shows_once_but_keeps_its_detail():
    """같은 판결이 두 일련번호로 실린 경우 화면에는 하나만, 조각은 둘 다 둬서 매주 다시 받지 않는다."""
    a, b = _rec(190296, no="2001가합7708", date="2002.05.16"), _rec(624197, no="2001가합7708", date="2002.05.16")
    idx, shards = prec_watch.build_outputs([a, b])
    assert len(idx["records"]) == 1
    assert str(a["id"]) in shards[prec_watch.shard_of(a["id"])]
    assert str(b["id"]) in shards[prec_watch.shard_of(b["id"])]


def test_duplicate_keeps_the_record_with_a_date_and_more_text():
    dated = _rec(1, no="2023누1", date="2024.01.01", issue="", gist="")
    undated = _rec(2, no="2023누1", date="", issue="긴 요지" * 5, gist="")
    assert prec_watch.same_case_ids([dated, undated]) == {2: 1}
    short = _rec(3, no="2023누2", date="2024.01.01", issue="짧음", gist="")
    long_ = _rec(4, no="2023누2", date="2024.01.01", issue="훨씬 긴 판시사항", gist="")
    assert prec_watch.same_case_ids([short, long_]) == {3: 4}


def test_shown_record_inherits_laws_and_tags_of_the_hidden_twin():
    """빼는 쪽으로만 찾히던 판례가 검색에서 사라지지 않는다."""
    keep = _rec(1, no="2023누1", date="2024.01.01", laws=["근로기준법"], tags=[])
    gone = _rec(2, no="2023누1", date="", laws=["산업재해보상보험법"], tags=["직장 내 괴롭힘"])
    idx, _ = prec_watch.build_outputs([keep, gone])
    assert [r["id"] for r in idx["records"]] == [1]
    assert idx["records"][0]["laws"] == ["근로기준법", "산업재해보상보험법"]
    assert idx["records"][0]["tags"] == ["직장 내 괴롭힘"]
    assert keep["laws"] == ["근로기준법"]


def test_three_records_of_one_judgment_show_once():
    recs = [_rec(i, no="2023누1", date="2024.01.01") for i in (1, 2, 3)]
    assert sorted(prec_watch.same_case_ids(recs)) == [1, 2]


def test_different_judgments_are_not_merged():
    """다른 법원, 다른 선고일, 사건번호 없는 기록은 합치지 않는다."""
    recs = [_rec(1, no="2001다1", court="대법원", date="2002.01.01"),
            _rec(2, no="2001다1", court="서울고등법원", date="2002.01.01"),
            _rec(3, no="2001다1", court="대법원", date="2003.01.01"),
            _rec(4, no="", date="2002.01.01"), _rec(5, no="", date="2002.01.01")]
    assert prec_watch.same_case_ids(recs) == {}
