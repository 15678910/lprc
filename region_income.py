# -*- coding: utf-8 -*-
"""⑫ 우리 지역 — 시도별 지역소득(KOSIS, 2020년 기준 계열).

'이 지역에서 만든 가치가 이 지역 사람의 소득으로 남는가'를 재는 세 가지를 모은다.

  DT_1C96  1인당 지역내총생산·지역총소득·가계총처분가능소득 (천원)
  DT_1C95  지역외순수취본원소득 (백만원) — 양수면 밖에서 들어온 소득, 음수면 밖으로 나간 소득
  DT_1C94  제도부문별 소득계정 (백만원) — 피용자보수(화면에서는 '노동자 보수')와 총본원소득잔액(=지역총소득)

화면 쪽(index.html rgCard)이 비율·순위를 계산한다. 여기서는 원자료를 시도×연도로 정리만 한다.
KOSIS_API_KEY 가 없으면 기존 docs/region.json 을 그대로 두고 끝낸다(exit 0).
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

OUT = "docs/region.json"
BASE = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
YEARS = 15
TIMEOUT = 45

# (표, 항목, 추가 분류, 응답 필드명 → 우리 키)
QUERIES = [
    ("DT_1C96", "T1+T2+T3", {}, {"T1": "pc_grdp", "T2": "pc_grni", "T3": "pc_hdi"}),
    ("DT_1C95", "T1", {}, {"T1": "net_inflow"}),
    ("DT_1C94", "T2", {"objL2": "A00+F00", "objL3": "00"}, {"A00": "comp", "F00": "gni"}),
]


def fetch(key, tbl, itm, extra):
    p = {"method": "getList", "apiKey": key, "orgId": "101", "tblId": tbl,
         "itmId": itm, "objL1": "ALL", "prdSe": "Y", "newEstPrdCnt": str(YEARS),
         "format": "json", "jsonVD": "Y"}
    p.update(extra)
    url = BASE + "?" + urllib.parse.urlencode(p, safe="+")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    data = json.loads(urllib.request.urlopen(req, timeout=TIMEOUT).read())
    if isinstance(data, dict):          # {"err": "...", "errMsg": "..."}
        raise RuntimeError(f"{tbl}: {data.get('errMsg') or data}")
    return data


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    key = (os.environ.get("KOSIS_API_KEY") or "").strip()
    if not key:
        print("  [INFO] KOSIS_API_KEY 없음 — ⑫ 지역소득 생략 (기존 파일 유지)")
        return 0

    regions = {}    # code -> {"name":..., "s": {year: {...}}}
    units = {}
    for tbl, itm, extra, keymap in QUERIES:
        try:
            rows = fetch(key, tbl, itm, extra)
        except Exception as e:
            print(f"  [ERR] {tbl} 조회 실패: {e} — 기존 파일 유지")
            return 0
        for r in rows:
            code = r.get("C1"); name = r.get("C1_NM"); yr = r.get("PRD_DE")
            # 1C94 는 항목이 분류(C2)에 있고, 나머지는 ITM_ID 에 있다
            k = keymap.get(r.get("C2")) if "objL2" in extra else keymap.get(r.get("ITM_ID"))
            if not (code and yr and k):
                continue
            try:
                v = float(r.get("DT"))
            except (TypeError, ValueError):
                continue
            units[k] = r.get("UNIT_NM")
            reg = regions.setdefault(code, {"code": code, "name": name, "s": {}})
            reg["s"].setdefault(yr, {})[k] = v
            # 표마다 시도 이름 표기가 다르다(강원도/강원특별자치도). 가장 최근 표기를 쓴다
            if name and ("특별자치" in name or not reg["name"]):
                reg["name"] = name
        print(f"  {tbl}: {len(rows)}행")

    years = sorted({y for reg in regions.values() for y in reg["s"]})
    # 전국(00)을 앞에, 나머지는 코드순
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
            "시도 단위 통계입니다. 시·군·구, 산업단지 단위로는 쪼개지지 않습니다.",
            "지역총소득은 거주지 기준, 지역내총생산은 생산지 기준입니다 — 두 값의 차이에는 본사 소재지 효과와 통근이 함께 섞여 있습니다.",
            "최근 연도는 잠정치이며 다음 발표에서 수정될 수 있습니다.",
        ],
        "regions": order,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"  저장 {OUT}: 시도 {len(order)}곳, {years[0]}~{years[-1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
