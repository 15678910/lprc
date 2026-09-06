# -*- coding: utf-8 -*-
"""⑫ 우리 지역 — 시도별 지역소득(KOSIS, 2020년 기준 계열) + 시도별 임금(사업체노동력조사).

'이 지역에서 만든 가치가 이 지역 사람의 소득으로 남는가'(구조, 연간·시차 1~2년)와
'이 지역 상용노동자는 지금 얼마를 받나'(현재에 더 가까운 값, 규모별)를 한 카드에 놓는다.

  통계청 101
    DT_1C96  1인당 지역내총생산·지역총소득·가계총처분가능소득 (천원)
    DT_1C95  지역외순수취본원소득 (백만원) — 양수면 밖에서 들어온 소득, 음수면 밖으로 나간 소득
    DT_1C94  제도부문별 소득계정 (백만원) — 피용자보수(화면에서는 '노동자 보수')와 총본원소득잔액(=지역총소득)
  고용노동부 118
    DT_118N_MON060  행정구역(시도)/산업/규모별 임금 및 근로시간 — 상용 월급여액·총근로시간,
                    전규모·1~29인·300인 이상. 연간 값이며 지역소득보다 한 해 앞선다.

화면 쪽(index.html rgCard)이 비율·순위를 계산한다. 여기서는 원자료를 정리만 한다.
KOSIS_API_KEY 가 없으면 기존 docs/region.json 을 그대로 두고 끝낸다(exit 0).
시군구 단위 임금 평균은 KOSIS 오픈API 에 없다(지역별고용조사는 취업자 수만) — 시도가 하한이다.
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

OUT = "docs/region.json"
BASE = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
TIMEOUT = 45

# 지역소득: (표, 항목, 추가 분류, 응답 필드 → 우리 키)
INCOME = [
    ("DT_1C96", "T1+T2+T3", {}, {"T1": "pc_grdp", "T2": "pc_grni", "T3": "pc_hdi"}),
    ("DT_1C95", "T1", {}, {"T1": "net_inflow"}),
    ("DT_1C94", "T2", {"objL2": "A00+F00", "objL3": "00"}, {"A00": "comp", "F00": "gni"}),
]
# 임금: 산업 '전체', 규모 셋. 항목 index5=상용월급여액(원), index2=상용총근로시간(시간)
WAGE_TBL = "DT_118N_MON060"
WAGE_PARAMS = {"itmId": "index5+index2", "objL1": "ALL",
               "objL2": "190326INDUSTRY_10S0",
               "objL3": "2024size_1+2024size_6+2024size_14"}
WAGE_SIZE = {"2024size_1": "all", "2024size_6": "small", "2024size_14": "large"}
WAGE_ITEM = {"index5": "pay", "index2": "hrs"}


def fetch(key, org, tbl, params, years):
    p = {"method": "getList", "apiKey": key, "orgId": org, "tblId": tbl,
         "prdSe": "Y", "newEstPrdCnt": str(years), "format": "json", "jsonVD": "Y"}
    p.update(params)
    url = BASE + "?" + urllib.parse.urlencode(p, safe="+")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    data = json.loads(urllib.request.urlopen(req, timeout=TIMEOUT).read())
    if isinstance(data, dict):          # {"err": "...", "errMsg": "..."}
        raise RuntimeError(f"{tbl}: {data.get('errMsg') or data}")
    return data


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def collect_income(key):
    regions, units = {}, {}
    for tbl, itm, extra, keymap in INCOME:
        rows = fetch(key, "101", tbl, dict(itmId=itm, objL1="ALL", **extra), 15)
        for r in rows:
            code, name, yr = r.get("C1"), r.get("C1_NM"), r.get("PRD_DE")
            # 1C94 는 항목이 분류(C2)에 있고, 나머지는 ITM_ID 에 있다
            k = keymap.get(r.get("C2")) if "objL2" in extra else keymap.get(r.get("ITM_ID"))
            v = num(r.get("DT"))
            if not (code and yr and k) or v is None:
                continue
            units[k] = r.get("UNIT_NM")
            reg = regions.setdefault(code, {"code": code, "name": name, "s": {}})
            reg["s"].setdefault(yr, {})[k] = v
            # 표마다 시도 이름 표기가 다르다(강원도/강원특별자치도). 가장 최근 표기를 쓴다
            if name and ("특별자치" in name or not reg["name"]):
                reg["name"] = name
        print(f"  {tbl}: {len(rows)}행")
    return regions, units


def collect_wage(key):
    rows = fetch(key, "118", WAGE_TBL, WAGE_PARAMS, 8)
    out, units = {}, {}
    for r in rows:
        name, yr = r.get("C1_NM"), r.get("PRD_DE")
        size, item = WAGE_SIZE.get(r.get("C3")), WAGE_ITEM.get(r.get("ITM_ID"))
        v = num(r.get("DT"))
        if not (name and yr and size and item) or v is None:
            continue
        units[item] = r.get("UNIT_NM")
        out.setdefault(name, {}).setdefault(yr, {})[f"{item}_{size}"] = v
    print(f"  {WAGE_TBL}: {len(rows)}행")
    return out, units


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    key = (os.environ.get("KOSIS_API_KEY") or "").strip()
    if not key:
        print("  [INFO] KOSIS_API_KEY 없음 — ⑫ 지역소득 생략 (기존 파일 유지)")
        return 0
    try:
        regions, units = collect_income(key)
    except Exception as e:
        print(f"  [ERR] 지역소득 조회 실패: {e} — 기존 파일 유지")
        return 0
    # 임금은 없어도 지역소득만으로 카드가 선다 — 실패해도 파일은 쓴다
    wage, wunits = {}, {}
    try:
        wage, wunits = collect_wage(key)
    except Exception as e:
        print(f"  [WARN] 임금 조회 실패: {e} — 임금 블록 없이 저장")

    years = sorted({y for reg in regions.values() for y in reg["s"]})
    order = sorted(regions.values(), key=lambda r: (r["code"] != "00", r["code"]))
    kst = timezone(timedelta(hours=9))
    out = {
        "generated_at": datetime.now(kst).isoformat(timespec="seconds"),
        "source": "통계청 지역소득(KOSIS) — 2020년 기준",
        "tables": {"DT_1C96": "시도별 1인당 지역내총생산·지역총소득·가계총처분가능소득",
                   "DT_1C95": "시도별 지역외순수취본원소득",
                   "DT_1C94": "시도별 제도부문별 소득계정(원천: 피용자보수·총본원소득잔액, 부문 합계)"},
        "units": units,
        "keys": {"pc_grdp": "1인당 지역내총생산", "pc_grni": "1인당 지역총소득",
                 "pc_hdi": "1인당 가계총처분가능소득", "net_inflow": "지역외순수취본원소득",
                 "comp": "노동자 보수(피용자보수)", "gni": "지역총소득(총본원소득잔액)"},
        "years": years,
        "limits": [
            "시도 단위 통계입니다. 시·군·구, 산업단지 단위로는 쪼개지지 않습니다(KOSIS 오픈API 에 시군구 임금 평균은 없습니다).",
            "지역총소득은 거주지 기준, 지역내총생산은 생산지 기준입니다 — 두 값의 차이에는 본사 소재지 효과와 통근이 함께 섞여 있습니다.",
            "최근 연도는 잠정치이며 다음 발표에서 수정될 수 있습니다.",
        ],
        "regions": order,
        "wage": {
            "source": "고용노동부 사업체노동력조사(KOSIS)",
            "table": WAGE_TBL,
            "note": "상용근로자 1인 이상 사업체, 산업 전체, 연간 월평균. 상용 월급여액 = 정액급여+초과급여+특별급여.",
            "units": wunits,
            "sizes": {"all": "전규모(1인 이상)", "small": "1~29인", "large": "300인 이상"},
            "years": sorted({y for d in wage.values() for y in d}),
            "regions": wage,      # 시도 짧은 이름(서울·충남…) → 연도 → {pay_all, pay_small, pay_large, hrs_*}
        } if wage else None,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"  저장 {OUT}: 시도 {len(order)}곳, 지역소득 {years[0]}~{years[-1]}"
          + (f", 임금 ~{out['wage']['years'][-1]}" if wage else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
