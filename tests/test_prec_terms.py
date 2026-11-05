"""판례 찾기 용어 사전·시나리오 형식 시험."""
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
    assert 25 <= len(TERMS) <= 35


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


def test_scenarios():
    assert len(SCEN) >= 20
    for s in SCEN:
        assert s["text"].strip()
        assert s["expect"], s["text"]
        for e in s["expect"]:
            assert e in IDS, (s["text"], e)
