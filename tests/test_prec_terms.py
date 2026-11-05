"""판례 찾기 용어 사전·시나리오 형식 시험.
(시나리오가 실제로 잡히는지는 tests/prec_search.test.js 가 본다.)"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as f:
        return json.load(f)


TERMS = _load("docs", "prec", "terms.json")["issues"]
SCEN = _load("tests", "prec_scenarios.json")
IDS = [i["id"] for i in TERMS]


def test_issue_count():
    assert 25 <= len(TERMS) <= 40


def test_ids_unique_lowercase():
    assert len(IDS) == len(set(IDS))
    assert all(re.fullmatch(r"[a-z][a-z0-9_]*", i) for i in IDS)
    assert "dismissal" in IDS


def test_issue_fields():
    for i in TERMS:
        assert i["name"].strip(), i["id"]
        assert len(i["field"]) >= 3, i["id"]
        assert len(i["terms"]) >= 1, i["id"]
        assert len(set(i["field"])) == len(i["field"]), i["id"]
        for law in i["laws"]:
            assert re.match(r"^.+ 제\d+조(의\d+)?$", law), (i["id"], law)


def test_phrases_clean():
    bad = []
    for i in TERMS:
        for k in ("field", "terms"):
            for p in i[k]:
                if not isinstance(p, str) or not p or p != p.strip():
                    bad.append((i["id"], k, p))
    assert not bad, bad


def test_scenarios_use_known_ids():
    assert len(SCEN) >= 20
    bad = []
    for s in SCEN:
        assert s["text"].strip()
        for e in s.get("expect", []) + s.get("forbid", []):
            if e not in IDS:
                bad.append((s["text"], e))
        # 쟁점 없는 문장은 expect 가 빈 배열이다(키는 있어야 한다)
        if "expect" not in s:
            bad.append((s["text"], "expect 키 없음"))
    assert not bad, bad
