# -*- coding: utf-8 -*-
"""업종·규모별 지불능력 기준선 — 한국은행 기업경영분석(KOSIS orgId 301, 2024년 기준).

④ 에서 회사가 공시에 없어 '직접 입력' 을 쓸 때, 매출·영업이익을 모르면 산식이 서지 않는다.
업종 평균이 있으면 "이 업종 중소기업의 매출액영업이익률 중위가 3.9% 이니, 매출 100억이면
영업이익 4억 남짓" 처럼 빈칸을 **추정치(그렇게 표시)** 로 채울 수 있다. ⑬ 국민연금 사업장에서는
가입자 × 신고소득 = 인건비 → 업종 인건비/매출액 비율로 매출 규모를 거꾸로 짚는 데 쓴다.

  DT_501Y006 손익 지표      매출액영업이익률(611) — 업종 × 규모 6종(종합·대·중견·중소·중·소)
  DT_501Y009 생산성 지표    부가가치율(9064)·노동소득분배율(9074)
                            → 인건비/매출액 = 부가가치율 × 노동소득분배율 (둘 다 비율이라 곱하면 된다)
  DT_501Y086 분위수         매출액영업이익률(611)·매출액증가율(506)의 평균·1분위·중위·3분위 — 규모 3종(종합·대·중소)

출력 docs/industry_finance.json (약 100KB). KOSIS_API_KEY 없으면 기존 파일 보존, exit 0.
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

OUT = "docs/industry_finance.json"
BASE = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
TIMEOUT = 90
SCALES = {"A": "종합", "L": "대기업", "J": "대기업(중견)", "M": "중소기업", "D": "중기업", "S": "소기업"}
QUART = {"A0000": "mean", "A1000": "q1", "A2000": "med", "A3000": "q3"}


def fetch(key, tbl, itm, extra, years):
    p = {"method": "getList", "apiKey": key, "orgId": "301", "tblId": tbl, "itmId": itm,
         "prdSe": "Y", "newEstPrdCnt": str(years), "format": "json", "jsonVD": "Y"}
    p.update(extra)
    url = BASE + "?" + urllib.parse.urlencode(p, safe="+.")
    data = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}),
                                             timeout=TIMEOUT).read())
    if isinstance(data, dict):
        raise RuntimeError(f"{tbl}: {data.get('errMsg') or data}")
    return data


def suffix(code):
    return (code or "").split(".")[-1]


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    key = (os.environ.get("KOSIS_API_KEY") or "").strip()
    if not key:
        print("  [INFO] KOSIS_API_KEY 없음 — 업종 평균 생략 (기존 파일 유지)")
        return 0

    names, data = {}, {}          # code -> name / code -> scale -> dict
    def put(code, scale, k, v):
        if v is None:
            return
        data.setdefault(code, {}).setdefault(scale, {})[k] = v

    try:
        # 손익 지표 — 최근 2년(전년 대비 방향을 보여주려고)
        rows = fetch(key, "DT_501Y006", "13103134573999",
                     {"objL1": "ALL", "objL2": "ALL", "objL3": "13102134573ACC_ITEM.611"}, 2)
        years = sorted({r["PRD_DE"] for r in rows})
        latest = years[-1]
        for r in rows:
            code, scale = suffix(r["C1"]), suffix(r["C2"])
            names[code] = r["C1_NM"]
            put(code, scale, "opm" if r["PRD_DE"] == latest else "opm_prev", num(r["DT"]))
        print(f"  Y006 손익지표 {len(rows)}행 {years}")

        rows = fetch(key, "DT_501Y009", "13103134679999",
                     {"objL1": "ALL", "objL2": "ALL",
                      "objL3": "13102134679ACC_ITEM.9064+13102134679ACC_ITEM.9074"}, 1)
        for r in rows:
            code, scale, acc = suffix(r["C1"]), suffix(r["C2"]), suffix(r["C3"])
            names.setdefault(code, r["C1_NM"])
            put(code, scale, {"9064": "va_rate", "9074": "labor_share"}[acc], num(r["DT"]))
        print(f"  Y009 생산성 {len(rows)}행")

        rows = fetch(key, "DT_501Y086", "13103136024999",
                     {"objL1": "ALL", "objL2": "ALL",
                      "objL3": "13102136024ACC_ITEM.611+13102136024ACC_ITEM.506", "objL4": "ALL"}, 1)
        for r in rows:
            code, scale, acc, qt = suffix(r["C1"]), suffix(r["C2"]), suffix(r["C3"]), suffix(r["C4"])
            names.setdefault(code, r["C1_NM"])
            if qt in QUART:
                put(code, scale, {"611": "opm_", "506": "growth_"}[acc] + QUART[qt], num(r["DT"]))
        print(f"  Y086 분위수 {len(rows)}행")
    except Exception as e:
        print(f"  [ERR] 조회 실패: {e} — 기존 파일 유지")
        return 0

    # 인건비/매출액 (추정) = 부가가치율 × 노동소득분배율
    for code, scales in data.items():
        for sc, d in scales.items():
            if d.get("va_rate") is not None and d.get("labor_share") is not None:
                d["labor_to_sales"] = round(d["va_rate"] * d["labor_share"] / 100, 2)

    order = sorted(names, key=lambda c: (c != "ZZZ00", c))     # 전산업(ZZZ00) 을 맨 앞에
    kst = timezone(timedelta(hours=9))
    out = {
        "generated_at": datetime.now(kst).isoformat(timespec="seconds"),
        "source": "한국은행 기업경영분석(KOSIS) — 제11차 표준산업분류, 법인기업 전수",
        "year": latest, "prev_year": years[0] if len(years) > 1 else None,
        "tables": {"DT_501Y006": "손익 지표", "DT_501Y009": "생산성 지표", "DT_501Y086": "분위수"},
        "scales": SCALES,
        "keys": {"opm": "매출액영업이익률(%, 평균)", "opm_prev": "전년 매출액영업이익률", "va_rate": "부가가치율(%)",
                 "labor_share": "노동소득분배율(% = 인건비÷부가가치)", "labor_to_sales": "인건비÷매출액(%, 추정 = 부가가치율×노동소득분배율)",
                 "opm_mean/q1/med/q3": "매출액영업이익률 분위(개별 기업 분포)", "growth_med": "매출액증가율 중위(%)"},
        "industries": [{"code": c, "name": names[c]} for c in order],
        "data": data,
        "limits": [
            "법인기업 전수(국세청 법인세 신고 기반) 평균입니다. 우리 회사가 평균과 같다는 보장은 없습니다 — 분위(1분위·중위·3분위)로 흩어짐을 함께 보세요.",
            "매출액영업이익률 '평균'은 큰 회사가 끌어올립니다. 회사 하나의 형편은 '중위'가 더 가깝습니다.",
            "인건비÷매출액은 부가가치율과 노동소득분배율을 곱해 낸 추정치입니다. 원자료에 직접 있는 값이 아닙니다.",
            f"기준 {latest}년 결산. 다음 해 결산은 이듬해 10~11월에 나옵니다.",
        ],
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"  저장 {OUT}: 업종 {len(order)}, 기준 {latest}년")
    return 0


if __name__ == "__main__":
    sys.exit(main())
