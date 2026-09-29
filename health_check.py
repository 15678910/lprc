# -*- coding: utf-8 -*-
"""사이트 건강 검진 — 배포된 단체교섭.kr 이 제대로 서 있는지 매일 확인한다.

자동 수집이 '성공'으로 끝나도 사이트가 멀쩡하다는 보장은 없다(배포 실패, 데이터가 며칠째 그대로,
인증서 만료, robots 설정이 풀림 …). 이 스크립트는 바깥에서 사이트를 방문자처럼 열어 본다.

점검
  1. 페이지 9개가 200 으로 열리고 <title> 이 있는가
  2. 매일 갱신 데이터가 너무 묵지 않았는가 (generated_at / checked_at 기준)
  3. HTTPS 인증서가 14일 이상 남았는가
  4. robots.txt 가 '기본 거부 + 검색엔진 허용' 을 유지하는가, sitemap.xml 이 열리는가

문제가 하나라도 있으면 exit 1 — 워크플로가 이슈를 연다. 표준 라이브러리만.
    python health_check.py
"""
import json
import os
import socket
import ssl
import sys
import urllib.request
import urllib.robotparser
from datetime import datetime, timedelta, timezone

HOST = "xn--9d0b29hf1nhhl.kr"          # 단체교섭.kr
BASE = f"https://{HOST}/"
PAGES = ["", "guide.html", "measure.html", "labor.html", "news.html", "ilo.html",
         "strategy.html", "future.html", "about.html"]
# (파일, 시각 필드, 허용 일수) — 매일 도는 수집은 하루 빠져도 경보가 울리지 않게 3일
FRESH = [("news.json", "generated_at", 3), ("law_watch.json", "checked_at", 3),
         ("money_macro.json", "generated_at", 3), ("public_sector.json", "generated", 8),
         ("region.json", "generated_at", 8), ("industry_finance.json", "generated_at", 8)]
KST = timezone(timedelta(hours=9))
UA = {"User-Agent": "lprc-health-check (+https://github.com/15678910/lprc)"}


def get(path, timeout=30):
    r = urllib.request.urlopen(urllib.request.Request(BASE + path, headers=UA), timeout=timeout)
    return r.status, r.read()


def parse_time(s):
    s = str(s).replace(" KST", "+09:00").strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S%z", "%Y-%m-%d"):
        try:
            d = datetime.strptime(s, fmt)
            return d if d.tzinfo else d.replace(tzinfo=KST)
        except ValueError:
            continue
    return None


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    now = datetime.now(KST)
    ok, bad = [], []

    for p in PAGES:
        try:
            st, body = get(p)
            (ok if st == 200 and b"<title>" in body else bad).append(f"페이지 /{p} — {st}")
        except Exception as e:
            bad.append(f"페이지 /{p} — 열리지 않음 ({e})")

    for f, key, days in FRESH:
        try:
            st, body = get(f + "?v=" + now.strftime("%H%M%S"))
            t = parse_time(json.loads(body).get(key, ""))
            if not t:
                bad.append(f"{f} — '{key}' 시각을 읽지 못함"); continue
            age = (now - t).total_seconds() / 86400
            msg = f"{f} — {t.strftime('%Y-%m-%d %H:%M')} ({age:.1f}일 전, 기준 {days}일)"
            (ok if age <= days else bad).append(msg)
        except Exception as e:
            bad.append(f"{f} — 불러오지 못함 ({e})")

    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((HOST, 443), timeout=20) as s:
            with ctx.wrap_socket(s, server_hostname=HOST) as ss:
                exp = datetime.strptime(ss.getpeercert()["notAfter"], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
        left = (exp - now).days
        (ok if left >= 14 else bad).append(f"인증서 — {exp.date()} 만료, {left}일 남음")
    except Exception as e:
        bad.append(f"인증서 — 확인 실패 ({e})")

    try:
        _, body = get("robots.txt")
        rp = urllib.robotparser.RobotFileParser(); rp.parse(body.decode("utf-8").splitlines())
        want = {"Googlebot": True, "Yeti": True, "GPTBot": False, "CCBot": False, "some-scraper": False}
        wrong = [ua for ua, allow in want.items() if rp.can_fetch(ua, BASE + "ilo.html") != allow]
        (bad if wrong else ok).append("robots.txt — " + ("의도와 다름: " + ", ".join(wrong) if wrong else "기본 거부 + 검색엔진 허용 유지"))
        st, _ = get("sitemap.xml")
        (ok if st == 200 else bad).append(f"sitemap.xml — {st}")
    except Exception as e:
        bad.append(f"robots/sitemap — 확인 실패 ({e})")

    lines = [f"## 사이트 건강 검진 — {now.strftime('%Y-%m-%d %H:%M')} KST", "",
             f"문제 {len(bad)}건 · 정상 {len(ok)}건", ""]
    lines += [f"- ❌ {x}" for x in bad] + [f"- ✅ {x}" for x in ok]
    report = "\n".join(lines)
    print(report)
    for path in (os.environ.get("GITHUB_STEP_SUMMARY"), os.environ.get("HEALTH_REPORT")):
        if path:
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(report + "\n")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
