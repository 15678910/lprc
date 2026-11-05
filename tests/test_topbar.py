"""모든 docs/*.html 머리띠 구조 검사 (표준 라이브러리만)."""
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

DOCS = Path(__file__).resolve().parent.parent / "docs"
PAGES = sorted(p for p in DOCS.glob("*.html") if "<!-- /topbar -->" in p.read_text(encoding="utf-8"))


class Bar(HTMLParser):
    def __init__(self):
        super().__init__()
        self.depth = 0
        self.opens = 0
        self.closes = 0
        self.stack = []          # (tag, attrs) 열린 div
        self.links = []          # (href, class, in_guide_sub)
        self.guide_sub_hrefs = []
        self.guide_parent_class = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "div":
            self.opens += 1
            self.stack.append(a)
        if tag == "a":
            href = a.get("href")
            in_sub = any("sub" in (d.get("class") or "").split() for d in self.stack) and \
                any("grp" in (d.get("class") or "").split() for d in self.stack) and self.cur_grp_is_guide
            self.links.append((href, a.get("class") or "", in_sub))
            if in_sub:
                self.guide_sub_hrefs.append(href)

    cur_grp_is_guide = False

    def handle_endtag(self, tag):
        if tag == "div":
            self.closes += 1
            if self.stack:
                self.stack.pop()


def bar_html(p):
    t = p.read_text(encoding="utf-8")
    i = t.index('class="topbar')
    return t[t.rfind("<div", 0, i + 1): t.index("<!-- /topbar -->")]


def parse(p):
    html = bar_html(p)
    # '원청교섭 가이드' grp 만 따로 표시하기 위해 그 grp 조각을 분리
    b = Bar()
    m = re.search(r'<div class="grp"><a href="\./labor\.html"[^>]*>원청교섭 가이드</a>', html)
    assert m, "원청교섭 가이드 .grp 없음"
    b.feed(html[:m.start()])
    pre_links = len(b.links)
    b.cur_grp_is_guide = True
    b.feed(html[m.start():])
    return html, b


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_topbar(page):
    html, b = parse(page)
    assert b.opens == b.closes, f"div 여닫이 불일치 {b.opens}/{b.closes}"
    assert "./strategy.html" in b.guide_sub_hrefs, "전략과 대안이 .sub 안에 없음"
    assert "./prec.html" in b.guide_sub_hrefs, "판례 찾기가 .sub 안에 없음"
    name = "./" + page.name
    own = [c for h, c, _ in b.links if h == name]
    if own:
        assert any("on" in c.split() for c in own), f"{page.name}: 현재 페이지 링크에 class=on 없음"
        if name in ("./strategy.html", "./prec.html"):
            assert re.search(r'<a href="\./labor\.html" class="on">원청교섭 가이드', html), "부모에 class=on 없음"
