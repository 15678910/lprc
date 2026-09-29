/* 사이트 공용 동작 — 머리띠 메뉴(☰·하위 메뉴), 사이트 검색, '맨 위로' 버튼.
   메뉴 링크는 각 HTML 에 정적으로 있으므로 이 파일이 없어도 이동은 된다.

   검색: 서버가 없다. 검색칸을 처음 쓸 때 같은 사이트의 문서 페이지를 한 번 불러와
   카드(.card > h2) 단위로 색인하고, 노동뉴스는 news.json 의 기사 제목을 색인한다.
   측정기(measure.html)는 화면이 스크립트로 그려지므로 홈의 '열세 화면' 목록으로 대신 색인한다.
   절 번호(id)는 sidenav.js 와 같은 규칙(card.id 가 없으면 'sec'+순번)으로 만든다 — 한쪽을 바꾸면 다른 쪽도. */
(function(){
  var bar = document.getElementById('topbar');

  /* ── 메뉴 ─────────────────────────────── */
  if (bar) {
    var btn = bar.querySelector('.burger');
    var setOpen = function(open){
      bar.classList.toggle('open', open);
      if (btn) { btn.setAttribute('aria-expanded', open ? 'true' : 'false'); btn.textContent = open ? '✕' : '☰'; }
    };
    if (btn) btn.addEventListener('click', function(e){ e.stopPropagation(); setOpen(!bar.classList.contains('open')); });
    bar.querySelectorAll('.menu a').forEach(function(a){ a.addEventListener('click', function(){ setOpen(false); }); });
    // 하위 메뉴 ▾ — 터치 화면에서는 마우스 올리기가 없으므로 눌러서 연다
    bar.querySelectorAll('.grp .caret').forEach(function(c){
      c.addEventListener('click', function(e){
        e.stopPropagation();
        var g = c.parentNode, open = !g.classList.contains('open');
        bar.querySelectorAll('.grp.open').forEach(function(x){ x.classList.remove('open'); });
        g.classList.toggle('open', open); c.setAttribute('aria-expanded', open ? 'true' : 'false');
      });
    });
    document.addEventListener('keydown', function(e){
      if (e.key === 'Escape') { setOpen(false); bar.querySelectorAll('.grp.open').forEach(function(x){ x.classList.remove('open'); }); hideResults(); }
    });
    document.addEventListener('click', function(e){
      if (!bar.contains(e.target)) { setOpen(false); hideResults(); }
      if (!e.target.closest || !e.target.closest('.grp')) bar.querySelectorAll('.grp.open').forEach(function(x){ x.classList.remove('open'); });
    });
  }

  /* ── 검색 ─────────────────────────────── */
  var PAGES = [['guide.html','소개'],['labor.html','원청교섭 가이드'],['strategy.html','전략과 대안'],
               ['ilo.html','현장과 ILO 기준'],['news.html','노동뉴스'],['future.html','AI 시대의 노동'],['about.html','출처 · 면책']];
  var input = bar && bar.querySelector('.search input');
  var box = bar && bar.querySelector('.search .results');
  var index = null, loading = null;

  function norm(s){ return (s || '').replace(/\s+/g, ' ').trim(); }
  function esc(s){ return String(s).replace(/[&<>"']/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
  function fetchText(u){ return fetch(u, {cache: 'no-cache'}).then(function(r){ return r.ok ? r.text() : ''; }).catch(function(){ return ''; }); }

  function buildIndex(){
    if (loading) return loading;
    var parser = new DOMParser(), items = [];
    var jobs = PAGES.map(function(p){
      return fetchText('./' + p[0]).then(function(html){
        if (!html) return;
        var d = parser.parseFromString(html, 'text/html');
        d.querySelectorAll('script,style,.topbar').forEach(function(x){ x.remove(); });
        var cards = Array.prototype.slice.call(d.querySelectorAll('.card')).filter(function(c){ return c.querySelector(':scope > h2'); });
        cards.forEach(function(c, i){
          var h = norm(c.querySelector(':scope > h2').textContent);
          items.push({kind: 'page', page: p[1], title: h, text: norm(c.textContent), url: './' + p[0] + '#' + (c.id || ('sec' + i))});
        });
        var sub = d.querySelector('header .sub, .hero p');
        if (sub) items.push({kind: 'page', page: p[1], title: p[1], text: norm(sub.textContent), url: './' + p[0]});
      });
    });
    jobs.push(fetchText('./').then(function(html){               // 측정기 열세 화면
      if (!html) return;
      var d = parser.parseFromString(html, 'text/html');
      d.querySelectorAll('a[href^="./measure.html#c"]').forEach(function(a){
        items.push({kind: 'page', page: '측정기', title: norm(a.childNodes[0].textContent), text: norm(a.textContent), url: a.getAttribute('href')});
      });
    }));
    jobs.push(fetch('./news.json', {cache: 'no-cache'}).then(function(r){ return r.ok ? r.json() : null; }).then(function(j){
      if (!j || !j.items) return;
      j.items.forEach(function(it){
        items.push({kind: 'news', page: '노동뉴스 · ' + it.date, title: it.title, text: it.title + ' ' + (it.cats || []).join(' '), url: it.link});
      });
    }).catch(function(){}));
    loading = Promise.all(jobs).then(function(){ index = items; return items; });
    return loading;
  }

  function search(q){
    var terms = norm(q).toLowerCase().split(' ').filter(Boolean);
    if (!terms.length) return [];
    var out = [];
    index.forEach(function(it){
      var t = it.title.toLowerCase(), b = it.text.toLowerCase(), score = 0;
      for (var k = 0; k < terms.length; k++) {
        var w = terms[k], inT = t.indexOf(w) >= 0, cnt = b.split(w).length - 1;
        if (!inT && !cnt) return;                            // 모든 낱말이 있어야 한다
        score += (inT ? 10 : 0) + Math.min(cnt, 5);
      }
      if (it.kind === 'news') score -= 3;                   // 사이트 본문을 기사보다 앞에
      out.push({it: it, score: score});
    });
    out.sort(function(a, b){ return b.score - a.score; });
    return out.slice(0, 12).map(function(x){ return x.it; });
  }

  function snippet(text, terms){
    var low = text.toLowerCase(), pos = -1;
    for (var k = 0; k < terms.length && pos < 0; k++) pos = low.indexOf(terms[k]);
    var s = Math.max(0, pos - 36), e = Math.min(text.length, (pos < 0 ? 0 : pos) + 84);
    var cut = (s > 0 ? '…' : '') + text.slice(s, e) + (e < text.length ? '…' : '');
    var h = esc(cut);
    terms.forEach(function(w){
      if (!w) return;
      h = h.replace(new RegExp(esc(w).replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi'), function(m){ return '<mark>' + m + '</mark>'; });
    });
    return h;
  }

  function hideResults(){ if (box) { box.hidden = true; box.innerHTML = ''; } }
  function render(q){
    if (!box) return;
    q = norm(q);
    if (q.length < 1) { hideResults(); return; }
    var terms = q.toLowerCase().split(' ').filter(Boolean);
    var res = search(q);
    if (!res.length) { box.innerHTML = '<div class="none">"' + esc(q) + '" — 찾지 못했습니다. 낱말을 줄이거나 바꿔 보세요.</div>'; box.hidden = false; return; }
    box.innerHTML = res.map(function(it, i){
      var ext = it.kind === 'news' ? ' target="_blank" rel="noopener noreferrer"' : '';
      return '<a href="' + esc(it.url) + '"' + ext + (i === 0 ? ' class="sel"' : '') + '>'
        + '<span class="pg">' + esc(it.page) + (it.kind === 'news' ? ' ↗' : '') + '</span>'
        + '<b>' + snippet(it.title, terms) + '</b>'
        + (it.kind === 'news' ? '' : '<span class="sn">' + snippet(it.text, terms) + '</span>') + '</a>';
    }).join('');
    box.hidden = false;
  }

  if (input && box) {
    var timer = null;
    input.addEventListener('focus', function(){ buildIndex(); });
    input.addEventListener('input', function(){
      clearTimeout(timer);
      var q = input.value;
      timer = setTimeout(function(){
        if (index) render(q);
        else { box.innerHTML = '<div class="none">색인을 만드는 중…</div>'; box.hidden = false; buildIndex().then(function(){ render(input.value); }); }
      }, 120);
    });
    input.addEventListener('keydown', function(e){
      var links = Array.prototype.slice.call(box.querySelectorAll('a'));
      if (!links.length) return;
      var i = links.findIndex(function(a){ return a.classList.contains('sel'); });
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        i = (i + (e.key === 'ArrowDown' ? 1 : -1) + links.length) % links.length;
        links.forEach(function(a, k){ a.classList.toggle('sel', k === i); });
        links[i].scrollIntoView({block: 'nearest'});
      } else if (e.key === 'Enter') {
        e.preventDefault(); (links[i >= 0 ? i : 0]).click();
      }
    });
    input.closest('form') && input.closest('form').addEventListener('submit', function(e){ e.preventDefault(); });
    box.addEventListener('click', function(e){ e.stopPropagation(); });
  }

  /* ── 맨 위로 ─────────────────────────── */
  var top = document.createElement('button');
  top.id = 'toTop'; top.type = 'button'; top.title = '맨 위로'; top.setAttribute('aria-label', '맨 위로');
  top.innerHTML = '<span>↑</span><small>TOP</small>';
  top.addEventListener('click', function(){ window.scrollTo({top: 0, behavior: 'smooth'}); });
  document.body.appendChild(top);
  var onScroll = function(){ top.classList.toggle('show', window.scrollY > 500); };
  window.addEventListener('scroll', onScroll, {passive: true});
  onScroll();
})();
