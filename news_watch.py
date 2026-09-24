# -*- coding: utf-8 -*-
"""📰 노동뉴스 — 국내 노동 관련 기사를 RSS 로 모아 갈래별로 나눈다.

싣는 것은 **제목·링크·출처·날짜뿐**이다. 본문은 저작권이 있고, 이 사이트의 일이 아니다.
description 은 갈래를 나누는 데만 쓰고 저장하지 않는다.

  출처 (RSS)                      비고
  매일노동뉴스 labortoday.co.kr   전 기사가 노동 — 그대로 싣는다
  법률신문 lawtimes.co.kr         법조 전반 — 노동 관련어가 있는 기사만 고른다

갈래는 제목(+요약)의 낱말로 나눈다. 규칙은 아래 CATS 에 그대로 있다 — 투명하지 않은 분류는
'왜 이게 여기 있나' 로 반박당한다. 한 기사가 여러 갈래에 들 수 있다.

출력 docs/news.json — 최근 60일치를 링크 기준으로 합쳐 둔다(이전 파일과 병합, 피드에서 빠져도 유지).
키 불필요. 피드 하나가 죽어도 나머지는 살린다.
"""
import html
import json
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

OUT = "docs/news.json"
KEEP_DAYS = 60
HDR = {"User-Agent": "Mozilla/5.0 (lprc news; +https://15678910.github.io/lprc/)"}

SOURCES = [
    {"id": "labortoday", "name": "매일노동뉴스", "url": "https://www.labortoday.co.kr",
     "rss": "https://www.labortoday.co.kr/rss/allArticle.xml", "labor_only": False},
    {"id": "lawtimes", "name": "법률신문", "url": "https://www.lawtimes.co.kr",
     "rss": "https://cdn.lawtimes.co.kr/rss/gn_rss_allArticle.xml", "labor_only": True},
]

# 법률신문처럼 법조 전반을 다루는 출처에서 노동 기사만 고르는 낱말
LABOR_WORDS = ["노동", "근로", "노조", "노동조합", "해고", "임금", "산재", "산업재해", "파업", "쟁의", "단체교섭",
               "단체협약", "노동위원회", "근로기준법", "노란봉투", "원청", "하청", "비정규", "정규직", "특수고용",
               "플랫폼 노동", "택배", "최저임금", "주52시간", "근로시간", "퇴직금", "체불", "괴롭힘", "노동자",
               "근로자", "고용노동부", "노동부", "고용", "부당노동행위", "통상임금", "중대재해", "직장 내"]

# 갈래 — 순서가 우선순위. (이름, 낱말들)
CATS = [
    ("판례·법리", ["대법원", "전원합의체", "헌법재판소", "헌재", "판결", "판시", "법리", "선고", "파기환송", "확정판결", "위헌", "합헌"]),
    ("재판·심판 진행", ["노동위원회", "지노위", "중노위", "구제신청", "판정", "결정", "소송", "기소", "재판", "항소", "상고", "고소", "고발",
                   "가처분", "집행정지", "행정소송", "송치", "수사", "특별근로감독", "근로감독"]),
    ("노동법·정책", ["개정", "입법", "법안", "시행령", "시행규칙", "국회", "환노위", "고용노동부", "노동부", "정책", "제도", "최저임금위",
                  "최저임금", "주52시간", "근로기준법", "노조법", "노란봉투", "노동법", "지침", "매뉴얼", "공포", "시행"]),
    ("사건·사고", ["산재", "산업재해", "사망", "사고", "추락", "끼임", "질식", "화재", "폭발", "과로사", "중대재해", "괴롭힘",
                "폭언", "폭행", "성희롱", "부상", "숨져", "숨진", "목숨"]),
    ("갈등·쟁의", ["파업", "쟁의", "농성", "집회", "결렬", "직장폐쇄", "단식", "투쟁", "시위", "점거", "천막", "총파업", "경고파업",
                "조정중지", "찬반투표", "대치", "반발", "규탄", "손배", "가압류"]),
    ("교섭·임금", ["교섭", "단협", "단체협약", "임금", "인상", "원청교섭", "임단협", "상여", "성과급", "통상임금", "체불",
                "인상률", "타결", "합의", "협약"]),
]


def fetch(url, timeout=40):
    return urllib.request.urlopen(urllib.request.Request(url, headers=HDR), timeout=timeout).read()


def strip(s):
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    return re.sub(r"\s+", " ", s).strip()


def parse_rss(raw):
    root = ET.fromstring(raw)
    out = []
    for it in root.iter("item"):
        title = strip(it.findtext("title"))
        link = (it.findtext("link") or "").strip()
        desc = strip(it.findtext("description"))
        pub = it.findtext("pubDate") or it.findtext("{http://purl.org/dc/elements/1.1/}date") or ""
        try:
            dt = parsedate_to_datetime(pub)
        except Exception:
            dt = None
        if title and link:
            out.append((title, link, desc, dt))
    return out


def classify(text):
    cats = [name for name, words in CATS if any(w in text for w in words)]
    return cats or ["기타"]


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    kst = timezone(timedelta(hours=9))
    now = datetime.now(kst)
    cutoff = now - timedelta(days=KEEP_DAYS)

    prev = {}
    if os.path.exists(OUT):
        try:
            for it in json.load(open(OUT, encoding="utf-8")).get("items", []):
                prev[it["link"]] = it
        except Exception:
            prev = {}

    items, diag = dict(prev), []
    for src in SOURCES:
        try:
            rows = parse_rss(fetch(src["rss"]))
        except Exception as e:
            diag.append(f"{src['name']}: 실패 — {e}")
            print(f"  [WARN] {src['name']} 실패: {e}")
            continue
        n_new = 0
        for title, link, desc, dt in rows:
            text = title + " " + desc[:300]
            if src["labor_only"] and not any(w in text for w in LABOR_WORDS):
                continue
            if link in items:
                continue
            date = (dt.astimezone(kst) if dt else now).strftime("%Y-%m-%d")
            items[link] = {"src": src["id"], "title": title, "link": link, "date": date, "cats": classify(text)}
            n_new += 1
        print(f"  {src['name']}: 피드 {len(rows)}건, 새 기사 {n_new}건")

    kept = [it for it in items.values() if it["date"] >= cutoff.strftime("%Y-%m-%d")]
    kept.sort(key=lambda x: (x["date"], x["title"]), reverse=True)
    out = {
        "generated_at": now.isoformat(timespec="seconds"),
        "keep_days": KEEP_DAYS,
        "sources": [{"id": s["id"], "name": s["name"], "url": s["url"], "rss": s["rss"], "labor_only": s["labor_only"]} for s in SOURCES],
        "categories": [c[0] for c in CATS] + ["기타"],
        "rules": {c[0]: c[1] for c in CATS},
        "labor_words": LABOR_WORDS,
        "telegram": "https://t.me/labornews_lprc",   # 채널 주소. 비어 있으면 화면에 구독 안내를 띄우지 않는다
        "note": "제목·링크·출처·날짜만 싣습니다. 본문은 각 언론사 페이지에서 읽으세요. 갈래는 낱말 규칙으로 나눈 것이라 틀릴 수 있습니다.",
        "diag": diag,
        "items": kept,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"  저장 {OUT}: {len(kept)}건 (최근 {KEEP_DAYS}일)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
