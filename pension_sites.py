# -*- coding: utf-8 -*-
"""⑬ 회사가 공시에 없을 때 — 국민연금 가입 사업장 내역(국민연금공단 공공데이터 개방).

DART 사업보고서는 상장·외감 법인만 낸다. 그 밖의 회사는 ④ 에서 찾을 수 없다.
국민연금 신고 자료는 **가입자 3인 이상 법인(개인 10인 이상) 전체**를 담고 있어서, 어느 회사든
'몇 명이 신고돼 있고 평균 신고소득이 얼마인지' 를 볼 수 있다. 정확한 임금은 아니지만
(상한 절단·전년도 소득 기준) 사측이 내놓는 숫자를 대조할 공개 자료다.

자료: 국민연금공단 '국민연금 가입 사업장 내역' 월간 ZIP(CSV, cp949, 약 36MB, 59만 사업장).
  API(NpsBplcInfoInqireService)는 2026-09 현재 '서비스 없음' 을 돌려줘 파일로 간다.
  게시판(모바일 사이트 공공데이터 개방)을 훑어 제목 '국민연금 가입 사업장 내역_YYYYMMDD' 중
  가장 최근 글의 첨부(FLxxxx)를 받는다. 이미 같은 날짜를 처리했으면 아무것도 안 한다.

출력 (표준 라이브러리만):
  docs/np/index.json      파일 날짜·시도 목록·전국 분포·한계
  docs/np/<시도코드>.json  가입자 30인 이상 사업장(근참법 노사협의회 의무 기준) — 화면이 시도 선택 후 받는다
  docs/np/industry.json   업종명별 평균 신고소득 분포(십분위) — '같은 업종 사업장 중 우리 위치'
키 불필요. 실패하면 기존 파일을 보존하고 exit 0.
"""
import csv
import io
import json
import os
import re
import statistics
import sys
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone, timedelta

OUT_DIR = "docs/np"
BASE = "https://m.nps.or.kr"
LIST = BASE + "/inforls/publdata/getOHAB0019M0List.do?menuId=MN24000873&hmpgCd=01&hmpgBbsCd=BS20240191&pageIndex={page}"
DOWN = BASE + "/fileDown.do?atchFileId={fl}&atchFileSn=1"
FALLBACK = ("20251024", "FL25002923")   # 게시판 탐색이 깨졌을 때
MIN_MEMBERS = 30                        # 근로자참여법 노사협의회 의무 기준과 같다
RATE = 0.09                             # 사업장가입자 보험료율(사용자 4.5 + 가입자 4.5)
CAP = 6_370_000                         # 기준소득월액 상한 (2025.7~2026.6)
HDR = {"User-Agent": "Mozilla/5.0"}
SIDO = {"11": "서울", "26": "부산", "27": "대구", "28": "인천", "29": "광주", "30": "대전", "31": "울산",
        "36": "세종", "41": "경기", "43": "충북", "44": "충남", "46": "전남", "47": "경북", "48": "경남",
        "50": "제주", "51": "강원", "52": "전북"}


def get(url, timeout=120):
    return urllib.request.urlopen(urllib.request.Request(url, headers=HDR), timeout=timeout).read()


def find_latest():
    """게시판 앞쪽 몇 쪽에서 '가입 사업장 내역_YYYYMMDD' 글을 찾아 (날짜, FL) 중 최신을 돌려준다."""
    found = []
    for page in range(1, 8):
        try:
            html = get(LIST.format(page=page), 60).decode("utf-8", "replace")
        except Exception as e:
            print(f"  [WARN] 목록 {page}쪽 실패: {e}")
            break
        rows = re.findall(r'<td class="title">\s*<a href="[^"]*">\s*(.*?)\s*</a>.*?fncAtchFileDownload\(\'(FL\d+)\'',
                          html, re.S)
        if not rows:
            break
        for title, fl in rows:
            m = re.search(r"가입 사업장 내역_(\d{8})", re.sub(r"\s+", " ", title))
            if m:
                found.append((m.group(1), fl))
    if not found:
        print("  [WARN] 게시판에서 못 찾음 — 알려진 파일로 간다")
        return FALLBACK
    return max(found)


def num(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def deciles(vals):
    v = sorted(vals)
    if not v:
        return []
    return [round(v[min(len(v) - 1, int(len(v) * k / 10))]) for k in range(1, 10)]


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.makedirs(OUT_DIR, exist_ok=True)
    idx_path = os.path.join(OUT_DIR, "index.json")
    prev = None
    if os.path.exists(idx_path):
        try:
            prev = json.load(open(idx_path, encoding="utf-8")).get("file_date")
        except Exception:
            prev = None

    date, fl = find_latest()
    print(f"  최신 파일 {date} ({fl}) / 보유 {prev}")
    if prev == date:
        print("  변경 없음 — 그대로 둔다")
        return 0

    try:
        blob = get(DOWN.format(fl=fl), 600)
        z = zipfile.ZipFile(io.BytesIO(blob))
        raw = z.read(z.namelist()[0])
    except Exception as e:
        print(f"  [ERR] 다운로드 실패: {e} — 기존 파일 유지")
        return 0
    text = raw.decode("cp949", "replace")
    rows = list(csv.reader(io.StringIO(text)))
    head, rows = rows[0], rows[1:]
    print(f"  {len(rows):,}행 · 열 {len(head)}")
    # 열 위치는 이름으로 잡는다 — 순서가 바뀌어도 살아남게
    col = {name.split(" ")[0]: i for i, name in enumerate(head)}
    c = lambda key: col[key]
    ym = rows[0][c("자료생성년월")] if rows else ""

    shards, all_inc, by_ind = {}, [], {}
    total_sites = 0
    for r in rows:
        if r[c("사업장가입상태코드")] != "1":
            continue
        total_sites += 1
        n = num(r[c("가입자수")])
        if n < MIN_MEMBERS:
            continue
        sido = r[c("법정동주소광역시도코드")]
        addr = (r[c("사업장지번상세주소")] or r[c("사업장도로명상세주소")]).split()
        sgg = " ".join(addr[1:2]) if len(addr) > 1 else ""
        ntc = num(r[c("당월고지금액")])
        rec = [r[c("사업장명")], r[c("사업자등록번호")], sgg, r[c("사업장업종코드명")],
               n, ntc, num(r[c("신규취득자수")]), num(r[c("상실가입자수")]), r[c("적용일자")],
               "법인" if r[c("사업장형태구분코드")] == "1" else "개인"]
        shards.setdefault(sido, []).append(rec)
        if n and ntc:
            inc = ntc / n / RATE
            all_inc.append(inc)
            by_ind.setdefault(rec[3], []).append(inc)

    for sido, recs in shards.items():
        recs.sort(key=lambda x: (-x[4], x[0]))
        with open(os.path.join(OUT_DIR, f"{sido}.json"), "w", encoding="utf-8") as f:
            json.dump(recs, f, ensure_ascii=False, separators=(",", ":"))
    ind = {k: {"n": len(v), "med": round(statistics.median(v)), "dec": deciles(v)}
           for k, v in by_ind.items() if len(v) >= 5}
    with open(os.path.join(OUT_DIR, "industry.json"), "w", encoding="utf-8") as f:
        json.dump(ind, f, ensure_ascii=False, separators=(",", ":"))

    kst = timezone(timedelta(hours=9))
    index = {
        "generated_at": datetime.now(kst).isoformat(timespec="seconds"),
        "source": "국민연금공단 공공데이터 개방 — 국민연금 가입 사업장 내역",
        "file_date": date, "data_ym": ym, "file_id": fl,
        "min_members": MIN_MEMBERS, "rate": RATE, "cap": CAP,
        "total_sites": total_sites, "sites": sum(len(v) for v in shards.values()),
        "fields": ["사업장명", "사업자번호앞6", "시군구", "업종명", "가입자수", "당월고지금액", "신규취득", "상실", "적용일자", "형태"],
        "sido": [{"code": k, "name": SIDO.get(k, k), "n": len(v)} for k, v in sorted(shards.items())],
        "all": {"n": len(all_inc), "med": round(statistics.median(all_inc)) if all_inc else None, "dec": deciles(all_inc)},
        "limits": [
            "가입자 30인 이상 사업장만 담았습니다(근로자참여법 노사협의회 설치 의무 기준과 같습니다).",
            "평균 신고소득 = 당월고지금액 ÷ 가입자수 ÷ 9%. 기준소득월액은 전년도 소득을 바탕으로 하고 상한(월 637만원)에서 잘리므로, 고임금 사업장은 실제보다 낮게 나옵니다.",
            "가입자수는 국민연금 신고 인원이라 실제 종사자(특수고용·초단시간·외국인 일부 제외)와 다를 수 있습니다.",
            "사업장 단위 신고라 본사·공장이 따로 등록된 회사는 여러 사업장으로 나뉩니다. 사업자번호 앞 6자리로 같은 회사인지 가늠하세요.",
            f"자료 기준월 {ym}. 국민연금공단이 이 파일을 매달 올리지는 않습니다 — 화면의 기준월을 확인하세요.",
        ],
    }
    with open(idx_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=1)
    print(f"  저장: 등록 {total_sites:,}곳 중 {index['sites']:,}곳(≥{MIN_MEMBERS}인), 시도 {len(shards)}, 업종 {len(ind)}, 기준월 {ym}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
