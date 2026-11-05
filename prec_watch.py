# -*- coding: utf-8 -*-
"""노동 법률 판례 수집기 — 법제처 DRF 목록·상세를 모아 docs/prec/ 정적 JSON 으로 낸다.

표준 라이브러리만. 키(OC)는 환경변수 LAW_OC 에서만 읽고 어떤 산출물에도 넣지 않는다.
흐름: 법별(표기 변형별) 전체 목록 훑기 → 일련번호로 합치기 → d/ 조각에 없는 판례만 상세 조회
(200건마다 저장 = 이어 받기) → 키·판례상세링크 검사와 축소 방지 후 쓰기.
상세 조회에 실패한 판례는 색인에 목록 필드로만 넣고 d 조각에는 넣지 않아 다음 실행에서 다시 시도한다.
인증 실패·키 누락은 재시도 없이 기존 파일을 보존하고 종료 코드 1.
"""
import argparse
import glob
import gzip
import json
import os
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import law_api

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "docs", "prec")
BASE = "https://www.law.go.kr/DRF/"
INTERVAL = 1.2          # 요청 간격(초) — 하한
TIMEOUT = 40
TRIES = 3
GIST_IN_INDEX = 300     # 색인 text 에 넣는 판결요지 앞부분 글자 수(0 이면 판시사항만)
SAVE_EVERY = 200
MAX_GZ = 2_000_000
SHRINK_MIN = 0.9        # 새 총수가 옛 총수의 90% 미만이면 쓰기 거부
UA = {"User-Agent": "Mozilla/5.0 (lprc prec_watch; +https://xn--9d0b29hf1nhhl.kr)"}

# 설계 측정표의 12개 법(산재보험법 제외)과 표기 변형. 변형별 건수는 로그로 남긴다.
VARIANTS = {
    "근로기준법": ["근로기준법"],
    "노동조합 및 노동관계조정법": ["노동조합 및 노동관계조정법", "노동조합법", "노동쟁의조정법",
                           "노동조합및노동관계조정법"],
    "근로자참여 및 협력증진에 관한 법률": ["근로자참여 및 협력증진에 관한 법률", "근로자참여및협력증진에관한법률"],
    "최저임금법": ["최저임금법"],
    "근로자퇴직급여 보장법": ["근로자퇴직급여 보장법", "근로자퇴직급여보장법"],
    "남녀고용평등과 일ㆍ가정 양립 지원에 관한 법률": [
        "남녀고용평등과 일ㆍ가정 양립 지원에 관한 법률", "남녀고용평등법", "남녀고용평등법"],
    "기간제 및 단시간근로자 보호 등에 관한 법률": [
        "기간제 및 단시간근로자 보호 등에 관한 법률", "기간제및단시간근로자보호등에관한법률"],
    "파견근로자 보호 등에 관한 법률": ["파견근로자 보호 등에 관한 법률", "파견근로자보호등에관한법률"],
    "산업안전보건법": ["산업안전보건법"],
    "임금채권보장법": ["임금채권보장법"],
    "고용보험법": ["고용보험법"],
    "근로복지기본법": ["근로복지기본법"],
}
LAWS = list(VARIANTS)

_last = [0.0]


def strip_html(s):
    s = re.sub(r"<br\s*/?>", "\n", s or "", flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("&nbsp;", " ").replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    return re.sub(r"[ \t]+", " ", re.sub(r"\s*\n\s*", "\n", s)).strip()


def shard_of(pid):
    return "%02d" % (pid % 100)


def to_record(item, detail, laws):
    """allowlist 로만 필드를 옮긴다(판례상세링크 등 나머지는 버린다)."""
    d = detail or {}
    return {
        "id": int(item.get("판례일련번호")),
        "no": strip_html(item.get("사건번호", "")),
        "name": strip_html(item.get("사건명", "")),
        "court": strip_html(item.get("법원명", "")),
        "date": strip_html(item.get("선고일자", "")),
        "type": strip_html(item.get("판결유형", "")),
        "issue": strip_html(d.get("판시사항", "")),
        "gist": strip_html(d.get("판결요지", "")),
        "refs": strip_html(d.get("참조조문", "")),
        "laws": sorted(laws),
    }


def build_outputs(records, failed=()):
    """(index, {shard: {id: {issue,gist,refs}}}). failed 의 id 는 d 조각에 넣지 않는다."""
    recs = sorted(records, key=lambda r: -r["id"])
    index = {"records": []}
    shards = {}
    for r in recs:
        text = r["issue"]
        if GIST_IN_INDEX > 0 and r["gist"]:
            text = (text + " " + r["gist"][:GIST_IN_INDEX]).strip()
        index["records"].append({"id": r["id"], "no": r["no"], "name": r["name"], "court": r["court"],
                                 "date": r["date"], "type": r["type"], "text": text, "laws": r["laws"]})
        if r["id"] in failed:
            continue
        shards.setdefault(shard_of(r["id"]), {})[str(r["id"])] = {
            "issue": r["issue"], "gist": r["gist"], "refs": r["refs"]}
    return index, shards


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def assert_no_key(text, oc):
    if oc and oc in text:
        raise RuntimeError("산출물에 키 문자열이 있다 — 쓰지 않는다")
    if re.search(r"OC=", text):
        raise RuntimeError("산출물에 OC= 패턴이 있다 — 쓰지 않는다")
    if "판례상세링크" in text:
        raise RuntimeError("산출물에 판례상세링크가 있다 — 쓰지 않는다")


def guard_shrink(new_total, old_total):
    if old_total > 0 and new_total < old_total * SHRINK_MIN:
        raise RuntimeError("판례 수가 %d → %d 로 급감 — 쓰지 않는다" % (old_total, new_total))


def write_if_changed(path, obj):
    data = dumps(obj).encode("utf-8")
    if os.path.exists(path):
        with open(path, "rb") as f:
            if f.read() == data:
                return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)
    return True


def _open(url):
    return law_api.open_law(url, dict(UA), TIMEOUT)


def fetch_json(url, oc):
    """https 전용·인증서 검증 켬. 인증 실패는 재시도 없이 LawAuthError."""
    if not url.startswith("https://"):
        raise RuntimeError("https 만 허용한다")
    last = None
    for i in range(TRIES):
        wait = _last[0] + INTERVAL - time.time()
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        try:
            data = json.loads(_open(url).decode("utf-8"))
        except Exception as e:
            last = RuntimeError("요청 실패: %s" % law_api.redact(str(e)))
            time.sleep(2 * (i + 1))
            continue
        return law_api.check_auth(data)
    raise last


def _url(page_kind, oc, **params):
    q = {"OC": oc, "target": "prec", "type": "JSON"}
    q.update(params)
    return BASE + page_kind + "?" + urllib.parse.urlencode(q)


def _as_list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def list_law(name, oc, limit=None):
    """한 표기로 검색한 전체 목록(참조법령명 JO)."""
    out, page = [], 1
    while True:
        data = fetch_json(_url("lawSearch.do", oc, JO=name, display=100, page=page), oc)
        items = _as_list((data.get("PrecSearch") or {}).get("prec"))
        out.extend(items)
        if len(items) < 100 or (limit and len(out) >= limit):
            return out
        page += 1


def load_existing(out):
    details = {}
    for p in glob.glob(os.path.join(out, "d", "*.json")):
        with open(p, encoding="utf-8") as f:
            for k, v in json.load(f).items():  # 조각의 영문 키를 응답의 한글 키로 되돌린다
                details[k] = {"판시사항": v.get("issue", ""), "판결요지": v.get("gist", ""),
                           "참조조문": v.get("refs", "")}
    total = 0
    mp = os.path.join(out, "meta.json")
    if os.path.exists(mp):
        with open(mp, encoding="utf-8") as f:
            total = int(json.load(f).get("total", 0))
    return details, total


def save(out, oc, items, laws_of, details, failed, old_total, check_shrink=True, force_meta=False):
    records = [to_record(items[i], details.get(str(i)), laws_of[i]) for i in sorted(items)]
    idx, shards = build_outputs(records, failed)
    by_law = {}
    for r in records:
        for lw in r["laws"]:
            by_law[lw] = by_law.get(lw, 0) + 1
    meta = {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "total": len(records), "by_law": by_law}
    files = {os.path.join(out, "index.json"): idx}
    for sh, obj in shards.items():
        files[os.path.join(out, "d", sh + ".json")] = obj
    for obj in files.values():
        assert_no_key(dumps(obj), oc)
    assert_no_key(dumps(meta), oc)
    if len(gzip.compress(dumps(idx).encode("utf-8"))) > MAX_GZ:
        raise RuntimeError("index.json 이 gzip 2MB 를 넘는다 — GIST_IN_INDEX 를 줄인다")
    if check_shrink:
        guard_shrink(len(records), old_total)
    changed = [write_if_changed(p, o) for p, o in files.items()]
    # 내용이 같으면 meta 의 generated_at 만 바뀌지 않게 건너뛴다
    mp = os.path.join(out, "meta.json")
    # force_meta: 끝까지 확인했으면 새 판례가 없어도 '확인한 시각'을 남긴다(건강 검진 신선도)
    if force_meta or any(changed) or not os.path.exists(mp):
        write_if_changed(mp, meta)
    return len(records)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    out = a.out or OUT
    try:
        oc = law_api.law_oc()
        items, laws_of = {}, {}
        for law, names in VARIANTS.items():
            ids_law = set()
            for nm in dict.fromkeys(names):
                got = list_law(nm, oc, a.limit or None)
                new = 0
                for it in got:
                    pid = int(it.get("판례일련번호"))
                    if pid not in ids_law:
                        new += 1
                    ids_law.add(pid)
                    items.setdefault(pid, it)
                    laws_of.setdefault(pid, set()).add(law)
                print("[%s] %s: %d건 (이 표기로 새로 늘어난 건 %d)" % (law, nm, len(got), new), flush=True)
            if a.limit and len(items) >= a.limit:
                break
        if a.limit:
            keep = sorted(items)[:a.limit]
            items = {i: items[i] for i in keep}
            laws_of = {i: laws_of[i] for i in keep}
        details, old_total = load_existing(out)
        todo = [i for i in sorted(items, reverse=True) if str(i) not in details]
        print("전체 %d건, 상세 조회 대상 %d건" % (len(items), len(todo)), flush=True)
        failed, done = set(), 0
        for pid in todo:
            try:
                data = fetch_json(_url("lawService.do", oc, ID=pid), oc)
                d = data.get("PrecService") or data
                if not isinstance(d, dict) or not any(k in d for k in ("판시사항", "판결요지", "참조조문")):
                    raise RuntimeError("상세 응답 형식 이상")
                details[str(pid)] = {k: d.get(k, "") for k in ("판시사항", "판결요지", "참조조문")}
            except law_api.LawAuthError:
                raise
            except RuntimeError as e:
                failed.add(pid)
                print("상세 실패 %d: %s" % (pid, law_api.redact(str(e))), flush=True)
            done += 1
            if done % SAVE_EVERY == 0:
                pending = failed | {i for i in todo if str(i) not in details}
                save(out, oc, items, laws_of, details, pending, old_total, not a.limit)
                print("중간 저장 %d/%d" % (done, len(todo)), flush=True)
        failed |= {i for i in items if str(i) not in details}
        n = save(out, oc, items, laws_of, details, failed, old_total, not a.limit, force_meta=True)
        print("저장 %d건 (상세 실패·미조회 %d건)" % (n, len(failed)), flush=True)
        return 0
    except RuntimeError as e:  # LawAuthError 포함
        print("중단: " + law_api.redact(str(e)), file=sys.stderr)
        return 1


def _fix_stdio():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass


if __name__ == "__main__":
    _fix_stdio()
    sys.exit(main())
