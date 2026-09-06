# -*- coding: utf-8 -*-
"""labor.html(원청교섭 가이드)의 기준 법령이 그대로인지 매일 확인한다.

가이드 본문은 사람이 쓰는 글이라 자동 갱신이 안 된다. 대신 '본문이 낡았는지'는
기계가 알 수 있다 — 본문이 기준으로 삼은 법령 3종의 공포번호가 국가법령정보센터에서
바뀌었는지만 대조하면 된다. 바뀌었으면 labor.html 이 화면에 경고를 띄운다.

- 조회: 법제처 DRF lawSearch (OC=test 로 열려 있음, 키 불필요)
- 판례·통계·행정해석의 변동은 이 방식으로 감지할 수 없다. 그 한계는 화면에 적어 두었다.
- 실패 시: 기존 docs/law_watch.json 을 건드리지 않고 그대로 종료한다(exit 0).
  워크플로의 다른 수집을 막지 않는다.
"""
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

OUT = "docs/law_watch.json"
TIMEOUT = 15

# labor.html 작성 시점(2026-09-06)의 기준 — 여기 값과 다르면 '개정됨'이다.
# 본문을 새 법령에 맞춰 고친 뒤에는 이 기준도 같이 올려야 경고가 꺼진다.
BASELINE = [
    ("노동조합 및 노동관계조정법",        "법",   21045, "20260310"),
    ("노동조합 및 노동관계조정법 시행령",  "영",   36159, "20260310"),
    ("노동조합 및 노동관계조정법 시행규칙", "규칙",   463, "20260310"),
]


def fetch_current(name):
    """법령명 정확 일치 + 현행인 항목의 (공포번호, 시행일자)를 돌려준다."""
    url = ("http://www.law.go.kr/DRF/lawSearch.do?OC=test&target=law&type=JSON"
           "&display=20&query=" + urllib.parse.quote(name))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    data = json.loads(urllib.request.urlopen(req, timeout=TIMEOUT).read())
    laws = data.get("LawSearch", {}).get("law", [])
    if isinstance(laws, dict):
        laws = [laws]
    for law in laws:
        if (law.get("법령명한글", "").strip() == name
                and law.get("현행연혁코드") == "현행"):
            return int(law.get("공포번호")), str(law.get("시행일자"))
    return None


def main():
    # Windows 콘솔(cp949)에서도 죽지 않게 — 워크플로에선 PYTHONIOENCODING 이 처리한다
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    kst = timezone(timedelta(hours=9))
    rows = []
    for name, short, base_no, base_eff in BASELINE:
        try:
            cur = fetch_current(name)
        except Exception as e:
            print(f"조회 실패({name}): {e} — 기존 파일을 보존하고 종료한다")
            return 0
        if cur is None:
            print(f"'{name}' 현행 항목을 못 찾았다 — 기존 파일을 보존하고 종료한다")
            return 0
        cur_no, cur_eff = cur
        rows.append({
            "name": name, "short": short,
            "baseline_pub_no": base_no, "baseline_eff_date": base_eff,
            "current_pub_no": cur_no, "current_eff_date": cur_eff,
            "changed": cur_no != base_no,
        })
    result = {
        "generated_at": datetime.now(kst).isoformat(timespec="seconds"),
        "checked_at": datetime.now(kst).strftime("%Y-%m-%d"),
        "source": "국가법령정보센터(law.go.kr) 법제처 DRF",
        "baseline_note": "labor.html 2026-09-06 작성 기준",
        "any_changed": any(r["changed"] for r in rows),
        "laws": rows,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    for r in rows:
        mark = "개정됨!" if r["changed"] else "그대로"
        print(f"{r['short']:2s} 공포 {r['current_pub_no']} 시행 {r['current_eff_date']} — {mark}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
