# -*- coding: utf-8 -*-
"""방문 통계(Cloudflare 웹 분석) 켜기 — 토큰 하나로 코드와 약속 문구를 함께 바꾼다.

    python .claude/tools/enable_analytics.py <사이트 토큰>

하는 일 (여러 번 돌려도 같은 결과 — 멱등)
  1. docs/site.js 의 CF_BEACON_TOKEN 에 토큰을 넣는다 → 모든 페이지가 비콘을 불러온다.
  2. docs/about.html 개인정보 절 — '분석 도구를 넣지 않았다' 를 방문 통계 설명으로 바꾼다
     (무엇을 모으고 무엇을 모으지 않는지, 목적, Cloudflare 방침 링크).
  3. docs/index.html 의 '출처 · 면책' 카드 소개, README 의 개인정보 설명을 맞춘다.
  4. 공용 파일 판 번호(?v=)를 올린다 — 브라우저가 옛 site.js 를 캐시에서 꺼내지 않게.

켜기 전에 약속 문구를 바꾸면 사실과 다른 말이 되므로, 문구는 반드시 이 도구로 코드와 함께 바꾼다.
"""
import datetime
import glob
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

if len(sys.argv) != 2 or not re.fullmatch(r"[0-9a-fA-F]{32}", sys.argv[1]):
    print("사용법: python .claude/tools/enable_analytics.py <32자리 16진수 토큰>")
    sys.exit(1)
TOKEN = sys.argv[1]
TODAY = datetime.date.today().isoformat()


def edit(path, fn):
    s = open(path, encoding="utf-8").read()
    t = fn(s)
    if t != s:
        open(path, "w", encoding="utf-8").write(t)
        print(path, "바뀜")
    else:
        print(path, "이미 적용됨")


# 1. 토큰
edit("docs/site.js", lambda s: re.sub(r"var CF_BEACON_TOKEN = '[0-9a-f]*';", "var CF_BEACON_TOKEN = '%s';" % TOKEN, s))

# 2. 출처 · 면책 — 개인정보 절
OLD_H2 = "<h2>개인정보 — 수집하지 않습니다</h2>"
NEW_H2 = "<h2>개인정보 — 입력값은 수집하지 않습니다</h2>"
OLD_SENT = "    별도의 분석 도구(Google Analytics 등)나 광고·추적 스크립트는 <b>넣지 않았습니다</b>.</div>"
NEW_BLOCK = """    광고·추적 스크립트는 <b>넣지 않았습니다</b>.</div>
  <h3 id="analytics">방문 통계 — 무엇을 모으고 무엇을 모으지 않나</h3>
  <p>%s부터 <b>Cloudflare 웹 분석</b>으로 방문 통계를 모읍니다. 이 사이트가 누구에게 어떻게 쓰이는지,
    어떤 화면이 도움이 되는지 알아 다음 개선과 알림 방향을 정하기 위해서입니다.</p>
  <table>
    <thead><tr><th>모으는 것</th><th>모으지 않는 것</th></tr></thead>
    <tbody>
      <tr><td>어떤 페이지를 몇 번 봤는지 · 어디서 링크를 타고 왔는지(유입 경로) · 국가 · 기기와 브라우저 종류 · 페이지 로딩 속도</td>
        <td>여러분이 <b>입력한 값</b>과 카드내역 · 이름·연락처 · <b>쿠키</b> · 방문자를 알아보거나 따라다니는 식별 정보</td></tr>
    </tbody>
  </table>
  <p class="muted" style="font-size:.92rem">통계는 방문 전체를 합친 숫자로만 봅니다. 입력한 값은 위 표대로 여전히 서버로 가지 않습니다.
    처리 방식은 <a href="https://www.cloudflare.com/privacypolicy/" target="_blank" rel="noopener noreferrer">Cloudflare 개인정보처리방침</a>을 따릅니다.</p>""" % TODAY


def about(s):
    s = s.replace(OLD_H2, NEW_H2)
    if 'id="analytics"' not in s:
        assert s.count(OLD_SENT) == 1, "about.html 약속 문구를 찾지 못했다 — 손으로 확인"
        s = s.replace(OLD_SENT, NEW_BLOCK)
    return s


edit("docs/about.html", about)

# 3. 홈 카드 · README
edit("docs/index.html", lambda s: s.replace("개인정보를 왜 수집하지 않는지.</p>",
                                           "입력값을 왜 수집하지 않는지, 방문 통계는 무엇을 모으는지.</p>"))


def readme(s):
    if "Cloudflare 웹 분석" in s:
        return s
    add = ("\n\n## 방문 통계\n\n"
           "%s부터 Cloudflare 웹 분석으로 방문 통계를 모읍니다(쿠키 없음, 개인 식별 없음, 입력값은 전송하지 않음).\n"
           "사이트의 역할·영향을 알아 다음 개선에 쓰기 위한 사용자 결정입니다. 토큰은 `docs/site.js` 의 `CF_BEACON_TOKEN`,\n"
           "켜고 끄기는 `.claude/tools/enable_analytics.py`.\n") % TODAY
    i = s.find("\n---\n\n## 라이선스")
    return s[:i] + add + s[i:] if i > 0 else s + add


edit("README.md", readme)

# 4. 판 번호
V = "a" + datetime.datetime.now().strftime("%Y%m%d%H%M")
for p in sorted(glob.glob("docs/*.html")):
    edit(p, lambda s: re.sub(r'\./(site\.css|site\.js|sidenav\.js)(\?v=\w+)?"', lambda m: './%s?v=%s"' % (m.group(1), V), s))
print("완료 — 커밋·푸시 후 배포본에서 static.cloudflareinsights.com 비콘이 불리는지 확인할 것")
