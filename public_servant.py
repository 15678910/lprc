"""공무원 임금교섭 근거자료 — 봉급표(인사혁신처) + 민간 대비 보수수준(지표누리)

왜 별도 화면인가
----------------
⑩ 공공부문(알리오)은 **공공기관** 직원을 다룬다. 공무원은 법적 지위도 교섭 구조도
다르다. 보수를 「공무원보수규정」(대통령령)이 정하므로, 공무원노조법 제10조에 따라
법령·조례·예산으로 정해지는 내용은 **단체협약으로서 효력이 없다**. 정부교섭대표는
그 내용이 이행되도록 성실히 노력할 의무만 진다.

그래서 근거의 목표가 다르다. "우리에게 이걸 달라"가 아니라 **"정부가 예산과
대통령령을 이렇게 바꿔야 하는 이유"**를 설득하는 자료여야 한다. 설득 대상도
사용자가 아니라 공무원보수위원회 → 기재부 예산 → 국무회의 라인과 여론이다.

그 라인이 실제로 움직인다는 증거가 있다. 공무원보수위원회는 2026년 본봉 인상률을
2.7~2.9%로 제시했으나 최종은 3.5%였다. 위원회 권고가 천장이 아니다.

가져오는 것
----------
1) 봉급표 — 인사혁신처. 키가 필요 없고 HTML 표로 그대로 들어 있다.
     https://www.mpm.go.kr/mpm/info/resultPay/bizSalary/{연도}/
   일반직·공안직·경찰소방·군인·교원·우정직 등 11종. 연도별 URL 규칙이 같다.

2) 민간 대비 공무원 보수수준 + 처우개선율 — 지표누리(e-나라지표).
   OpenAPI 는 승인 심사가 필요하지만, **화면이 실제로 쓰는 주소는 키가 필요 없다.**
     /unity/potal/eNara/sub/showStblGams3.do?stts_cd=102101&idx_cd=1021&freq=Y&period=N
   출처는 인사혁신처 『민·관 보수수준 실태조사』.

   민간 100인 이상 사업체 사무·관리직 임금을 100 으로 놓은 값이다.
   2020년 90.5% → 2022년 83.1% 로 2년 만에 7.4%p 떨어진 뒤 회복되지 않았다.
   처우개선율이 2021년 0.9%·2022년 1.4% 였던 시기와 겹친다.

⚠️ 한계
  · 봉급표는 **본봉만**이다. 정액급식비·직급보조비 같은 수당은 「공무원수당 등에 관한
    규정」(대통령령) 소관이라 여기 없다. 실수령액과 다르다.
  · 표 구조가 해마다 조금씩 바뀐다(2023년 이전에는 20종). 그래서 해석하지 않고
    **머리행과 데이터행을 그대로** 담는다. 화면이 필요한 표만 골라 쓴다.
  · 접근율은 조사 설계상 민간 100인 이상 사무관리직이 기준이다. 전체 민간 평균이 아니다.

출력: docs/public_servant.json
🚨 어느 쪽 주장도 대변하지 않는 계산 결과 · 노무·법률 자문 아님.
"""

import html
import json
import os
import re
import ssl
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(BASE_DIR, "docs", "public_servant.json")
# 원본 표 전체(11~20종 × 6년)는 163KB 다. ⑪ 은 일반직만 쓰므로 갈라 둔다.
# 경찰·소방·교원·군인 표를 붙일 때 이 파일만 더 받으면 된다.
PAY_FILE = os.path.join(BASE_DIR, "docs", "public_servant_pay.json")

PAY_URL = "https://www.mpm.go.kr/mpm/info/resultPay/bizSalary/%d/"
IDX_URL = ("https://www.index.go.kr/unity/potal/eNara/sub/showStblGams3.do"
           "?stts_cd=102101&idx_cd=1021&freq=Y&period=N")
UA = {"User-Agent": "Mozilla/5.0 (compatible; lprc-public-servant)"}

YEARS_BACK = 5          # 올해 포함 최근 6개 연도
TIMEOUT = 15            # 닿지 않을 때 오래 매달리지 않는다(알리오에서 배운 것)
TRIES = 2

DIAG = []


def log(m):
    print(m, flush=True)


def diag(kind, msg):
    DIAG.append({"kind": kind, "msg": msg})
    log("[%s] %s" % (kind, msg))


def _get(url, referer=None, timeout=TIMEOUT, tries=TRIES):
    h = dict(UA)
    if referer:
        h["Referer"] = referer
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    last = None
    for i in range(tries):
        try:
            r = urllib.request.Request(url, headers=h)
            return urllib.request.urlopen(r, context=ctx, timeout=timeout).read()
        except Exception as e:
            last = e
            if i + 1 < tries:
                time.sleep(1.0)
    raise last


def _text(s):
    """태그를 걷어내고 엔티티를 푼다. 표 안에 <br> 과 &nbsp; 가 섞여 있다."""
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def _tables(doc):
    """<table> 을 캡션·머리행·데이터행으로 쪼갠다.

    표마다 구조가 달라(교원표는 호봉이 두 벌씩 들어간다) 해석하지 않는다.
    있는 그대로 담아 두고 화면이 골라 쓰게 한다."""
    out = []
    for m in re.finditer(r"<table[^>]*>(.*?)</table>", doc, re.S):
        blk = m.group(1)
        cap = re.search(r"<caption[^>]*>(.*?)</caption>", blk, re.S)
        cap = _text(cap.group(1)) if cap else ""
        rows = []
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", blk, re.S):
            cells = [_text(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]
            if any(cells):
                rows.append(cells)
        if len(rows) >= 2:
            out.append({"caption": cap, "head": rows[0], "rows": rows[1:]})
    return out


def _num(s):
    s = re.sub(r"[^\d.]", "", s or "")
    try:
        return float(s) if s else None
    except ValueError:
        return None


def pay_tables(year):
    """한 해 봉급표. 없는 해(내년 등)는 조용히 건너뛴다."""
    try:
        doc = _get(PAY_URL % year).decode("utf-8", "replace")
    except Exception as e:
        diag("WARN", "%d년 봉급표 조회 실패: %s" % (year, str(e)[:60]))
        return None
    tabs = _tables(doc)
    if not tabs:
        diag("WARN", "%d년 봉급표에 표가 없다 — 아직 공표 전이거나 화면이 바뀌었다." % year)
        return None
    return tabs


def general_grade(tabs):
    """일반직 표에서 계급 × 호봉을 뽑는다. ⑪ 이 기본으로 쓰는 표다.

    머리행이 ['계급','1급',...,'9급'] 이고 각 행이 ['1 호봉', 값...] 형태다.
    구조가 바뀌면 None 을 돌려 화면이 원본 표로 넘어가게 한다."""
    for t in tabs:
        if "일반직공무원" not in t["caption"]:
            continue
        grades = [g for g in t["head"] if re.search(r"\d\s*급", g)]
        if not grades:
            return None
        steps = {}
        for r in t["rows"]:
            m = re.match(r"(\d+)", r[0] or "")
            if not m:
                continue
            vals = [_num(x) for x in r[1:1 + len(grades)]]
            if any(v for v in vals):
                steps[int(m.group(1))] = vals
        if steps:
            return {"grades": grades, "steps": steps}
    return None


def approach_rate():
    """민간 대비 공무원 보수수준 · 처우개선율 (지표누리, 키 불필요)."""
    try:
        doc = _get(IDX_URL, referer="https://www.index.go.kr/").decode("utf-8", "replace")
    except Exception as e:
        diag("WARN", "지표누리 조회 실패: %s" % str(e)[:60])
        return None
    years, series = [], {}
    for t in _tables(doc):
        for r in [t["head"]] + t["rows"]:
            cells = [c for c in r if c]
            if not cells:
                continue
            ys = [c for c in cells if re.fullmatch(r"(19|20)\d{2}", c)]
            if len(ys) >= 4 and not years:
                years = ys
                continue
            if not years:
                continue
            name = cells[0]
            vals = [_num(c) for c in cells[1:1 + len(years)]]
            if "보수수준" in name or "처우개선" in name:
                if sum(1 for v in vals if v is not None) >= 3:
                    key = "approach" if "보수수준" in name else "raise_pct"
                    series[key] = dict((y, v) for y, v in zip(years, vals) if v is not None)
    if not series.get("approach"):
        diag("WARN", "지표누리에서 '민간 대비 보수수준' 행을 못 찾음 — 화면이 바뀌었다.")
        return None
    return {"years": years, **series,
            "source": "지표누리 e-나라지표 1021 · 인사혁신처 『민·관 보수수준 실태조사』",
            "definition": ("민간 100인 이상 사업체 사무·관리직 임금을 100 으로 놓았을 때의 "
                           "공무원 보수 수준. 전체 민간 평균이 아니다."),
            }


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # type: ignore
        except Exception:
            pass
    now = datetime.now(KST)
    log("=" * 60)
    log("  공무원 임금교섭 근거자료 (봉급표 + 민간 대비 보수수준)")
    log("=" * 60)

    this_year = now.year
    years = list(range(this_year - YEARS_BACK, this_year + 1))
    pay, gen = {}, {}
    for y in years:
        tabs = pay_tables(y)
        time.sleep(0.3)
        if not tabs:
            continue
        pay[str(y)] = tabs
        g = general_grade(tabs)
        if g:
            gen[str(y)] = g
            lo = g["steps"].get(1)
            log("  %d년 · 표 %2d종 · 일반직 %d계급 × %d호봉 · 9급1호봉 %s원"
                % (y, len(tabs), len(g["grades"]), len(g["steps"]),
                   format(int(lo[-1]), ",") if lo and lo[-1] else "?"))
        else:
            log("  %d년 · 표 %2d종 (일반직 구조를 못 읽어 원본만 담는다)" % (y, len(tabs)))

    if not pay:
        diag("ERROR", "봉급표를 한 해도 받지 못했다 — 기존 파일을 보존하고 끝낸다.")
        return 1

    idx = approach_rate()
    if idx:
        ys = idx["years"]
        a = idx["approach"]
        log("  민간 대비 보수수준 %s년 %.1f%% → %s년 %.1f%%"
            % (ys[0], a[ys[0]], ys[-1], a[ys[-1]]))

    # 원본 표는 따로 낸다 — ⑪ 이 쓰는 것은 일반직뿐이다.
    with open(PAY_FILE, "w", encoding="utf-8") as f:
        json.dump({"generated": now.isoformat(), "pay": pay},
                  f, ensure_ascii=False, separators=(",", ":"))

    out = {
        "generated": now.isoformat(),
        "years": [y for y in years if str(y) in pay],
        "tables": dict((y, [t["caption"] for t in ts]) for y, ts in pay.items()),
        "pay_file": "./public_servant_pay.json",
        "general": gen,             # 연도 → 일반직 계급×호봉 (화면 기본)
        "index": idx,               # 접근율·처우개선율
        "sources": {
            "pay": "인사혁신처 공무원 봉급표 (mpm.go.kr) — 키 불필요",
            "index": "지표누리 e-나라지표 1021 (index.go.kr) — 키 불필요",
        },
        "limits": [
            "봉급표는 **본봉만**이다. 정액급식비·직급보조비 등 수당은 「공무원수당 등에 "
            "관한 규정」 소관이라 여기 없다. 실수령액과 다르다.",
            "공무원노조법 제10조에 따라 법령·조례·예산으로 정해지는 내용은 단체협약으로서 "
            "효력이 없다. 보수는 「공무원보수규정」(대통령령) 사항이라 단협으로 정할 수 없고, "
            "정부교섭대표는 이행되도록 성실히 노력할 의무만 진다. "
            "이 화면은 교섭 문안이 아니라 예산·법령을 바꿀 근거를 만드는 자료다.",
            "민간 대비 보수수준은 민간 100인 이상 사업체 **사무·관리직** 임금이 기준이다. "
            "전체 민간 평균이 아니므로 '민간보다 몇 % 낮다'로 옮겨 말하면 안 된다.",
        ],
        "diag": DIAG,
    }
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    tmp = OUTPUT_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, OUTPUT_FILE)
    log("  저장 목록 %.0fKB + 원본 표 %.0fKB"
        % (os.path.getsize(OUTPUT_FILE) / 1024, os.path.getsize(PAY_FILE) / 1024))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
