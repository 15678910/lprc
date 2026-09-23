# -*- coding: utf-8 -*-
"""📰 노동뉴스 텔레그램 발송 — docs/news.json 의 새 기사를 채널에 한 번에 올린다.

방식: 개인에게 보내지 않는다. **채널**(공개든 비공개든)에 봇이 게시하고, 받고 싶은 사람은 채널을
구독한다. 구독자 명단을 우리가 갖지 않으니 개인정보가 없고, 탈퇴도 스스로 한다.

필요한 것 (GitHub Secrets):
  TELEGRAM_BOT_TOKEN   @BotFather 가 준 토큰
  TELEGRAM_CHAT_ID     채널 아이디 — 공개 채널이면 '@채널이름', 비공개면 '-100…' 숫자
둘 중 하나라도 없으면 아무것도 하지 않는다(exit 0).

보낸 기사는 docs/news_sent.json 에 링크로 기록해 두 번 보내지 않는다. 한 번에 최대 25건,
4,000자 안에서 여러 메시지로 나눈다. 표준 라이브러리만.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

NEWS = "docs/news.json"
SENT = "docs/news_sent.json"
MAX_ITEMS = 25
MAX_CHARS = 3900
SRC_NAME = {"labortoday": "매일노동뉴스", "lawtimes": "법률신문"}


def esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def send(token, chat, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = urllib.parse.urlencode({"chat_id": chat, "text": text, "parse_mode": "HTML",
                                   "disable_web_page_preview": "true"}).encode()
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, data=body), timeout=30)
        return json.loads(r.read()).get("ok", False)
    except urllib.error.HTTPError as e:
        # 텔레그램은 이유를 본문에 준다(chat not found / bot is not a member / can't parse entities …).
        # 토큰은 URL 에만 있으므로 본문을 찍어도 새지 않는다.
        try:
            why = json.loads(e.read()).get("description", "")
        except Exception:
            why = ""
        raise RuntimeError(f"HTTP {e.code} {why}") from None


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    if not token or not chat:
        print("  [INFO] TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 없음 — 발송 생략")
        return 0
    if not chat.startswith("@") and not chat.lstrip("-").isdigit():
        chat = "@" + chat            # 사용자명을 @ 없이 넣은 경우
    print(f"  chat_id 형식: {'채널 사용자명' if chat.startswith('@') else '숫자 ID'} (길이 {len(chat)})")
    if not os.path.exists(NEWS):
        print("  news.json 없음"); return 0
    news = json.load(open(NEWS, encoding="utf-8"))
    sent = set()
    if os.path.exists(SENT):
        try:
            sent = set(json.load(open(SENT, encoding="utf-8")).get("links", []))
        except Exception:
            sent = set()
    first_run = not sent
    new = [it for it in news.get("items", []) if it["link"] not in sent]
    if first_run:
        # 처음 켤 때 60일치를 한꺼번에 쏟지 않는다 — 최신 것만 보내고 나머지는 '보낸 것'으로 친다
        new = new[:MAX_ITEMS]
    if not new:
        print("  새 기사 없음"); return 0
    new = new[:MAX_ITEMS]

    kst = timezone(timedelta(hours=9))
    head = f"📰 <b>노동뉴스</b> {datetime.now(kst).strftime('%m/%d')} · 새 기사 {len(new)}건\n"
    lines, msgs, cur = [], [], head
    for it in new:
        cat = it["cats"][0] if it.get("cats") else ""
        line = f"• [{esc(cat)}] <a href=\"{esc(it['link'])}\">{esc(it['title'])}</a> <i>— {esc(SRC_NAME.get(it['src'], it['src']))}</i>\n"
        if len(cur) + len(line) > MAX_CHARS:
            msgs.append(cur); cur = ""
        cur += line
    cur += "\n제목·링크만 보냅니다. 본문은 각 언론사에서. 모아보기: https://15678910.github.io/lprc/news.html"
    msgs.append(cur)

    ok = True
    for m in msgs:
        try:
            ok = send(token, chat, m) and ok
        except Exception as e:
            print(f"  [ERR] 발송 실패: {e}"); ok = False; break
    if ok:
        links = list(sent | {it["link"] for it in news.get("items", [])} if first_run else sent | {it["link"] for it in new})
        with open(SENT, "w", encoding="utf-8") as f:
            json.dump({"updated": datetime.now(kst).isoformat(timespec="seconds"), "links": links[-3000:]}, f, ensure_ascii=False)
        print(f"  발송 {len(new)}건 ({len(msgs)}개 메시지)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
