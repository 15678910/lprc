# -*- coding: utf-8 -*-
"""노동 법률 판례 수집기 — 법제처 DRF 목록·상세를 모아 docs/prec/ 정적 JSON 으로 낸다.

표준 라이브러리만. 키(OC)는 환경변수 LAW_OC 에서만 읽고 어떤 산출물에도 넣지 않는다.
흐름: 법별(표기 변형별) 전체 목록 훑기 → 일련번호로 합치기 → d/ 조각에 없는 판례만 상세 조회
(200건마다 저장 = 이어 받기) → 키·판례상세링크 검사와 축소 방지 후 쓰기.
상세 조회에 실패한 판례는 색인에 목록 필드로만 넣고 d 조각에는 넣지 않아 다음 실행에서 다시 시도한다.
판결문 본문(판례내용)은 terms.json 의 body 표현이 들어 있는지만 확인해 tags 로 남기고, 원문은 어떤 산출물에도 넣지 않는다.
표현 목록이 바뀌면(tv 불일치) 상세를 다시 받아 확인한다. 다시 확인 실패는 기존 상세를 그대로 둔다.
인증 실패·키 누락은 재시도 없이 기존 파일을 보존하고 종료 코드 1.
"""
import argparse
import glob
import hashlib
import gzip
import json
import os
import re
import sys
import time
import urllib.parse
from datetime import datetime, timezone

import law_api

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "docs", "prec")
TERMS = os.path.join(OUT, "terms.json")
BASE = "https://www.law.go.kr/DRF/"
INTERVAL = 1.2          # 요청 간격(초) — 하한
TIMEOUT = 40
TRIES = 3
GIST_IN_INDEX = 300     # 색인 text 에 넣는 판결요지 앞부분 글자 수(0 이면 판시사항만)
SAVE_EVERY = 200
MAX_GZ = 2_000_000
SHRINK_MIN = 0.9        # 새 총수가 옛 총수의 90% 미만이면 쓰기 거부
UA = {"User-Agent": "Mozilla/5.0 (lprc prec_watch; +https://xn--9d0b29hf1nhhl.kr)"}

# 수집하는 13개 법: 설계 측정표의 12개 법(산재보험법 제외)에 근로복지기본법을 더했다
# (첫 수집에서 이미 13건이 들어와 유지하기로 함). 법마다 표기 변형을 두고 변형별 건수는 로그로 남긴다.
VARIANTS = {
    "근로기준법": ["근로기준법"],
    "노동조합 및 노동관계조정법": ["노동조합 및 노동관계조정법", "노동조합법", "노동쟁의조정법",
                           "노동조합및노동관계조정법"],
    "근로자참여 및 협력증진에 관한 법률": ["근로자참여 및 협력증진에 관한 법률", "근로자참여및협력증진에관한법률"],
    "최저임금법": ["최저임금법"],
    "근로자퇴직급여 보장법": ["근로자퇴직급여 보장법", "근로자퇴직급여보장법"],
    "남녀고용평등과 일ㆍ가정 양립 지원에 관한 법률": [
        "남녀고용평등과 일ㆍ가정 양립 지원에 관한 법률", "남녀고용평등법"],
    "기간제 및 단시간근로자 보호 등에 관한 법률": [
        "기간제 및 단시간근로자 보호 등에 관한 법률", "기간제및단시간근로자보호등에관한법률"],
    "파견근로자 보호 등에 관한 법률": ["파견근로자 보호 등에 관한 법률", "파견근로자보호등에관한법률"],
    "산업안전보건법": ["산업안전보건법"],
    "임금채권보장법": ["임금채권보장법"],
    "고용보험법": ["고용보험법"],
    "근로복지기본법": ["근로복지기본법"],
    "노동위원회법": ["노동위원회법"],
}
LAWS = list(VARIANTS)

_last = [0.0]


def strip_html(s):
    s = re.sub(r"<br\s*/?>", "\n", s or "", flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("&nbsp;", " ").replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    return re.sub(r"[ \t]+", " ", re.sub(r"\s*\n\s*", "\n", s)).strip()


def body_phrases(path):
    """terms.json 의 body 표현을 중복 없이 정렬해 모은다. 파일이 없거나 0개면 RuntimeError(대체값 없음)."""
    try:
        with open(path, encoding="utf-8") as f:
            issues = json.load(f).get("issues", [])
    except (OSError, ValueError) as e:
        raise RuntimeError("terms.json 을 읽지 못했다: %s" % e.__class__.__name__)
    out = set()
    for i in issues:
        for b in i.get("body") or []:
            if isinstance(b, str) and b.strip():
                out.add(b)
    if not out:
        raise RuntimeError("terms.json 에 body 표현이 없다")
    return sorted(out)


def tags_version(phrases):
    return hashlib.sha1("\n".join(phrases).encode("utf-8")).hexdigest()[:8]


def _squash(s):
    return re.sub(r"\s+", "", s)


def body_tags(text, phrases):
    """text(판례내용·판시사항·판결요지를 이은 글)에 들어 있는 표현을 terms.json 표기 그대로 정렬해 돌려준다."""
    t = _squash(strip_html(text))
    return sorted(p for p in phrases if _squash(p) and _squash(p) in t)


def shard_of(pid):
    return "%02d" % (pid % 100)


def clean_date(s):
    """법제처의 '0001.01.01' 은 선고일 없음의 표시다. 화면에 날짜처럼 내보내지 않는다."""
    s = strip_html(s)
    digits = re.sub(r"\D", "", s)
    return "" if not digits or digits.startswith("0001") else s


def to_record(item, detail, laws):
    """allowlist 로만 필드를 옮긴다(판례상세링크 등 나머지는 버린다).
    근로복지공단 산재판례는 목록에 사건번호·법원이 비어 있고 상세에만 있어 상세로 채운다."""
    d = detail or {}
    no = strip_html(item.get("사건번호", ""))
    rec = {
        "id": int(item.get("판례일련번호")),
        "no": no or strip_html(d.get("사건번호", "")),
        "name": strip_html(item.get("사건명", "")),
        "court": strip_html(item.get("법원명", "")) or strip_html(d.get("법원명", "")),
        "date": clean_date(item.get("선고일자", "")),
        "type": strip_html(item.get("판결유형", "")),
        "issue": strip_html(d.get("판시사항", "")),
        "gist": strip_html(d.get("판결요지", "")),
        "refs": strip_html(d.get("참조조문", "")),
        "laws": sorted(laws),
        "tags": list(d.get("tags") or []),
        "tv": d.get("tv") or "",
    }
    if (not no or not strip_html(item.get("법원명", ""))) and "사건번호" in d:
        rec["meta_from_detail"] = True  # 내부 표시. 색인에는 나가지 않고 조각 기록에만 쓴다
    return rec


def same_case_ids(records):
    """같은 판결이 법제처에 두 일련번호로 실린 경우 화면에서 뺄 id.
    법원·사건번호가 같고 선고일이 같거나 한쪽에 없으면 같은 판결이다.
    선고일이 있고 글이 긴 쪽을 남긴다. 사건번호가 없으면 판단하지 않는다."""
    best = sorted(records, key=lambda r: (bool(r["date"]), len(r["issue"]) + len(r["gist"]), len(r["tags"]), r["id"]),
                  reverse=True)
    kept, hide = {}, set()
    for r in best:
        if not r["no"]:
            continue
        dates = kept.setdefault((r["court"], r["no"]), [])
        if any(d == r["date"] or not r["date"] for d in dates):
            hide.add(r["id"])
        else:
            dates.append(r["date"])
    return hide


def build_outputs(records, failed=()):
    """(index, {shard: {id: {issue,gist,refs,tags,tv}}}). failed 의 id 는 d 조각에 넣지 않는다.
    같은 판결의 겹친 기록은 색인에서만 뺀다. 조각에 두어야 다음 실행에서 상세를 다시 받지 않는다."""
    recs = sorted(records, key=lambda r: -r["id"])
    hide = same_case_ids(recs)
    index = {"records": []}
    shards = {}
    for r in recs:
        text = r["issue"]
        if GIST_IN_INDEX > 0 and r["gist"]:
            text = (text + " " + r["gist"][:GIST_IN_INDEX]).strip()
        row = {"id": r["id"], "no": r["no"], "name": r["name"], "court": r["court"],
               "date": r["date"], "type": r["type"], "text": text, "laws": r["laws"]}
        if r["tags"]:
            row["tags"] = r["tags"]
        if r["id"] not in hide:
            index["records"].append(row)
        if r["id"] in failed:
            continue
        entry = {"issue": r["issue"], "gist": r["gist"], "refs": r["refs"], "tags": r["tags"], "tv": r["tv"]}
        if r.get("meta_from_detail"):  # 목록에 없는 값이라 조각에 남겨야 다음 실행에서 사라지지 않는다
            entry["no"], entry["court"] = r["no"], r["court"]
        shards.setdefault(shard_of(r["id"]), {})[str(r["id"])] = entry
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


def fetch_json(url):
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
        data = fetch_json(_url("lawSearch.do", oc, JO=name, display=100, page=page))
        items = _as_list((data.get("PrecSearch") or {}).get("prec"))
        out.extend(items)
        if len(items) < 100 or (limit and len(out) >= limit):
            return out
        page += 1


def needs_recheck(item, det, tv):
    """표지 판이 다르거나, 목록에 사건번호·법원이 비었는데 상세에서 받아 둔 적도 없으면 다시 조회한다."""
    if det.get("tv") != tv:
        return True
    blank = not strip_html(item.get("사건번호", "")) or not strip_html(item.get("법원명", ""))
    return blank and "사건번호" not in det


def load_existing(out):
    details = {}
    for p in glob.glob(os.path.join(out, "d", "*.json")):
        with open(p, encoding="utf-8") as f:
            for k, v in json.load(f).items():  # 조각의 영문 키를 응답의 한글 키로 되돌린다
                details[k] = {"판시사항": v.get("issue", ""), "판결요지": v.get("gist", ""),
                           "참조조문": v.get("refs", ""), "tags": v.get("tags", []), "tv": v.get("tv", "")}
                if "no" in v:
                    details[k]["사건번호"], details[k]["법원명"] = v["no"], v.get("court", "")
    total = 0
    mp = os.path.join(out, "meta.json")
    if os.path.exists(mp):
        with open(mp, encoding="utf-8") as f:
            total = int(json.load(f).get("total", 0))
    return details, total


def save(out, oc, items, laws_of, details, failed, old_total, check_shrink=True, force_meta=False,
         recheck_failed=0):
    records = [to_record(items[i], details.get(str(i)), laws_of[i]) for i in sorted(items)]
    idx, shards = build_outputs(records, failed)
    by_law = {}
    for r in records:
        for lw in r["laws"]:
            by_law[lw] = by_law.get(lw, 0) + 1
    meta = {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "total": len(records), "shown": len(idx["records"]), "by_law": by_law,
            "failed": len(failed), "recheck_failed": recheck_failed}
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
    if a.limit and not a.out:  # 몇십 건만 모은 색인으로 실제 docs/prec 를 덮어쓰지 않게 한다
        ap.error("--limit 은 --out 과 함께만 쓴다(실제 docs/prec 를 덮어쓰지 않도록)")
    out = a.out or OUT
    try:
        oc = law_api.law_oc()
        phrases = body_phrases(TERMS)
        tv = tags_version(phrases)
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
        recheck = [i for i in sorted(items, reverse=True)
                   if str(i) in details and needs_recheck(items[i], details[str(i)], tv)]
        print("전체 %d건, 상세 조회 대상 %d건, 본문 표지 다시 확인 대상 %d건" % (len(items), len(todo), len(recheck)),
              flush=True)
        failed, done, recheck_failed, no_body = set(), 0, 0, 0
        recheck_set = set(recheck)
        queue = todo + recheck
        for pid in queue:
            try:
                data = fetch_json(_url("lawService.do", oc, ID=pid))
                d = data.get("PrecService") or data
                if not isinstance(d, dict) or not any(k in d for k in ("판시사항", "판결요지", "참조조문")):
                    raise RuntimeError("상세 응답 형식 이상")
                nd = {k: d.get(k, "") for k in ("판시사항", "판결요지", "참조조문")}
                nd["사건번호"], nd["법원명"] = d.get("사건번호") or "", d.get("법원명") or ""
                nd["tags"] = body_tags(" ".join(str(d.get(k) or "") for k in ("판례내용", "판시사항", "판결요지")),
                                       phrases)
                if str(d.get("판례내용") or "").strip():
                    nd["tv"] = tv
                else:  # 본문이 없으면 확인을 마친 것이 아니다 — tv 를 비워 다음 실행에서 다시 확인한다
                    nd["tv"] = ""
                    no_body += 1
                details[str(pid)] = nd
            except law_api.LawAuthError:
                raise
            except RuntimeError as e:
                if pid in recheck_set:  # 기존 상세를 그대로 두고, 다음 실행에서 다시 확인한다
                    recheck_failed += 1
                else:
                    failed.add(pid)
                print("상세 실패 %d%s: %s" % (pid, "(다시 확인)" if pid in recheck_set else "",
                                          law_api.redact(str(e))), flush=True)
            done += 1
            if done % SAVE_EVERY == 0:
                pending = failed | {i for i in todo if str(i) not in details}
                save(out, oc, items, laws_of, details, pending, old_total, not a.limit, recheck_failed=recheck_failed)
                print("중간 저장 %d/%d" % (done, len(queue)), flush=True)
        failed |= {i for i in items if str(i) not in details}
        n = save(out, oc, items, laws_of, details, failed, old_total, not a.limit, force_meta=True,
                 recheck_failed=recheck_failed)
        print("저장 %d건 (상세 실패·미조회 %d건, 다시 확인 실패 %d건, 본문 없음 %d건)" % (n, len(failed), recheck_failed, no_body),
              flush=True)
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
