/* 판례 찾기 화면. 입력값은 전송·저장하지 않고, 외부 자료는 textContent 로만 넣는다. */
(function (root) {
  'use strict';
  var PAGE = 20;
  var NO_GIST = '요지가 없는 판례입니다. 원문을 보세요.';

  // ---- 순수 로직(DOM 없이 시험 가능) ----
  function shardName(id) {
    var n = Number(id);
    if (!isFinite(n) || n < 0 || Math.floor(n) !== n) return null;
    return ('0' + (n % 100)).slice(-2);
  }
  function lawUrl(id) {
    var s = String(id);
    if (!/^\d+$/.test(s)) return null;
    return 'https://www.law.go.kr/LSW/precInfoP.do?precSeq=' + s;
  }
  // 요지 → 판시사항 → 안내 문구
  function pickGist(entry) {
    var e = entry || {};
    var g = String(e.gist || '').trim();
    if (g) return { text: g, kind: 'gist' };
    var i = String(e.issue || '').trim();
    if (i) return { text: i, kind: 'issue' };
    return { text: NO_GIST, kind: 'none' };
  }
  function preview(rec, max) {
    var t = String((rec && rec.text) || '').trim();
    if (!t) return NO_GIST;
    return t.length > max ? t.slice(0, max) + '…' : t;
  }
  function titleLine(r) {
    return [r.court, r.no].filter(Boolean).join(' ') + ' · ' + (r.date || '') + ' · ' + (r.name || '');
  }
  // 일치한 낱말 + 그 쟁점의 관련 조문(중복 제거). 최대 max 개.
  function matchedLine(matched, issues, max) {
    var out = [], seen = {};
    function add(x) { if (x && !seen[x]) { seen[x] = 1; out.push(x); } }
    (matched || []).forEach(add);
    (issues || []).forEach(function (is) {
      var hit = (is.terms || []).some(function (t) { return (matched || []).indexOf(t) !== -1; });
      if (hit) (is.laws || []).forEach(add);
    });
    return out.slice(0, max || 6);
  }
  function sinceYearFor(now) { return now.getFullYear() - 10; }

  var logic = { shardName: shardName, lawUrl: lawUrl, pickGist: pickGist, preview: preview,
                titleLine: titleLine, matchedLine: matchedLine, sinceYearFor: sinceYearFor, NO_GIST: NO_GIST };
  if (typeof module !== 'undefined' && module.exports) { module.exports = logic; return; }
  if (typeof document === 'undefined') return;

  // ---- 화면 ----
  var $ = function (id) { return document.getElementById(id); };
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  var data = null, loading = null, shards = {};
  var st = { text: '', selected: [], shown: PAGE, adding: false, searched: false };

  function fetchJson(url) {
    return fetch(url, { credentials: 'omit', referrerPolicy: 'no-referrer' }).then(function (r) {
      if (!r.ok) throw new Error(String(r.status));
      return r.json();
    });
  }
  function load() {
    if (data) return Promise.resolve(data);
    if (!loading) {
      loading = Promise.all([fetchJson('./prec/meta.json'), fetchJson('./prec/index.json'), fetchJson('./prec/terms.json')])
        .then(function (a) {
          data = { meta: a[0], records: Array.isArray(a[1]) ? a[1] : (a[1].records || []), issues: a[2].issues || [] };
          return data;
        }, function (e) { loading = null; throw e; });
    }
    return loading;
  }
  function loadShard(n) {
    if (!shards[n]) {
      shards[n] = fetchJson('./prec/d/' + n + '.json').catch(function (e) { delete shards[n]; throw e; });
    }
    return shards[n];
  }

  function showError(on) { $('err').hidden = !on; }

  function search() {
    var text = $('q').value;
    st.text = text;
    st.shown = PAGE;
    $('go').disabled = true;
    showError(false);
    load().then(function (d) {
      st.selected = PrecSearch.detectIssues(text, d.issues);
      st.searched = true;
      st.adding = false;
      render();
    }, function () { showError(true); }).then(function () { $('go').disabled = false; });
  }

  function render() {
    if (!data || !st.searched) return;
    $('out').hidden = false;
    renderChips();
    var m = data.meta || {};
    var total = Number(m.total);
    var day = String(m.generated_at || '').slice(0, 10);
    $('meta').textContent = '수록 ' + (isFinite(total) ? total.toLocaleString('ko-KR') : '?') + '건 · 기준 ' + (day || '?') + ' · 산재·노동위 결정은 아직 없음';
    var res = PrecSearch.rank(data.records, {
      issues: st.selected, text: st.text,
      courtOnly: $('fc').checked, sinceYear: $('fy').checked ? sinceYearFor(new Date()) : 0
    });
    renderList(res);
  }

  function renderChips() {
    var box = $('chips');
    box.textContent = '';
    box.appendChild(el('span', 'lbl', st.selected.length ? '이렇게 이해했습니다' : '잡힌 쟁점이 없습니다. 아래에서 고르거나 입력한 낱말로 찾습니다.'));
    st.selected.forEach(function (is) {
      var c = el('span', 'chip');
      c.appendChild(el('span', null, is.name));
      var x = el('button', 'x', '×');
      x.type = 'button';
      x.setAttribute('aria-label', is.name + ' 빼기');
      x.addEventListener('click', function () {
        st.selected = st.selected.filter(function (s) { return s !== is; });
        st.shown = PAGE; render();
      });
      c.appendChild(x);
      box.appendChild(c);
    });
    var add = el('button', 'chip addb', '+ 쟁점 추가');
    add.type = 'button';
    add.setAttribute('aria-expanded', String(st.adding || !st.selected.length));
    add.addEventListener('click', function () { st.adding = !st.adding; renderChips(); });
    box.appendChild(add);
    var pick = $('pick');
    pick.textContent = '';
    pick.hidden = !(st.adding || !st.selected.length);
    if (pick.hidden) return;
    data.issues.forEach(function (is) {
      if (st.selected.indexOf(is) !== -1) return;
      var b = el('button', 'chip', is.name);
      b.type = 'button';
      b.addEventListener('click', function () {
        st.selected.push(is); st.adding = false; st.shown = PAGE; render();
      });
      pick.appendChild(b);
    });
  }

  function renderList(res) {
    var list = $('list');
    list.textContent = '';
    $('count').textContent = res.length ? ('찾은 판례 ' + res.length.toLocaleString('ko-KR') + '건 중 ' + Math.min(st.shown, res.length).toLocaleString('ko-KR') + '건 표시') : '';
    if (!res.length) list.appendChild(el('p', 'empty', '맞는 판례를 찾지 못했습니다. 쟁점을 더하거나 다른 낱말로 다시 적어 보세요.'));
    res.slice(0, st.shown).forEach(function (x) { list.appendChild(card(x)); });
    var more = $('more');
    more.hidden = res.length <= st.shown;
    more.onclick = function () { st.shown += PAGE; renderList(res); };
  }

  function card(x) {
    var r = x.record;
    var c = el('div', 'rec');
    c.appendChild(el('div', 'rt', titleLine(r)));
    var ml = matchedLine(x.matched, st.selected, 6);
    if (ml.length) c.appendChild(el('div', 'rm', '일치: ' + ml.join(' · ')));
    var body = el('div', 'rb', preview(r, 140));
    c.appendChild(body);
    var acts = el('div', 'ra');
    var tg = el('button', 'btn', '요지 펼치기');
    tg.type = 'button';
    tg.setAttribute('aria-expanded', 'false');
    var open = false, full = el('div', 'rfull');
    full.hidden = true;
    tg.addEventListener('click', function () {
      open = !open;
      tg.setAttribute('aria-expanded', String(open));
      tg.textContent = open ? '요지 접기' : '요지 펼치기';
      full.hidden = !open;
      if (!open || full.dataset.ok) return;
      full.textContent = '불러오는 중…';
      var sn = shardName(r.id);
      (sn ? loadShard(sn) : Promise.resolve({})).then(function (sh) {
        var g = pickGist(sh[String(r.id)]);
        full.textContent = '';
        if (g.kind === 'issue') full.appendChild(el('div', 'rk', '판결요지가 없어 판시사항을 보여 드립니다.'));
        full.appendChild(el('div', null, g.text));
        if (g.kind !== 'gist') full.appendChild(el('div', 'rk', '자세한 내용은 원문을 보세요.'));
        full.dataset.ok = '1';
      }, function () {
        full.textContent = '요지를 불러오지 못했습니다. 다시 눌러 보거나 원문을 보세요.';
        delete full.dataset.ok; // 칸이 열린 채이므로 라벨('요지 접기')·aria-expanded 도 열림 그대로. 접었다 다시 펼치면 재시도
      });
    });
    acts.appendChild(tg);
    var u = lawUrl(r.id);
    if (u) {
      var a = el('a', 'btn', '원문 보기 ↗');
      a.href = u; a.target = '_blank'; a.rel = 'noopener noreferrer';
      acts.appendChild(a);
    }
    c.appendChild(acts);
    c.appendChild(full);
    return c;
  }

  function init() {
    $('f').addEventListener('submit', function (e) { e.preventDefault(); search(); });
    $('retry').addEventListener('click', search);
    $('fc').addEventListener('change', function () { st.shown = PAGE; render(); });
    $('fy').addEventListener('change', function () { st.shown = PAGE; render(); });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})(typeof window !== 'undefined' ? window : this);
