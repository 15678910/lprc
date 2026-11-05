/* 판례 찾기 검색 엔진 — 브라우저 안에서만 돈다. 입력값을 어디로도 보내지 않는다. */
(function (root) {
  'use strict';
  var MAX_INPUT = 5000;
  var MAX_WORDS = 50;

  // 가운뎃점만 지운다. 공백은 지우지 않는다(어절 경계를 넘는 오탐 방지).
  function norm(s) { return String(s == null ? '' : s).split('·').join('').split('ㆍ').join('').split('・').join(''); }
  function isSpace(c) { return c === 32 || (c >= 9 && c <= 13) || c === 160 || c === 12288; }

  // 사전 표현을 공백으로 나눈 조각 목록.
  function pieces(phrase) {
    var out = [], cur = '';
    for (var i = 0; i < phrase.length; i++) {
      if (isSpace(phrase.charCodeAt(i))) { if (cur) out.push(cur); cur = ''; } else cur += phrase[i];
    }
    if (cur) out.push(cur);
    return out;
  }

  // 조각이 입력에 순서대로, 조각 사이에는 공백(0개 이상)만 두고 나타나면 true. 첫 조각의 모든 위치를 시도한다.
  function matchPieces(t, ps) {
    var from = 0;
    for (;;) {
      var at = t.indexOf(ps[0], from);
      if (at === -1) return false;
      var pos = at + ps[0].length, ok = true;
      for (var k = 1; k < ps.length; k++) {
        while (pos < t.length && isSpace(t.charCodeAt(pos))) pos++;
        if (t.substr(pos, ps[k].length) !== ps[k]) { ok = false; break; }
        pos += ps[k].length;
      }
      if (ok) return true;
      from = at + 1;
    }
  }

  function matchPhrase(text, phrase) {
    var ps = pieces(norm(phrase));
    if (!ps.length) return false;
    return matchPieces(norm(text), ps);
  }

  // 입력 전체에서 앞뒤 공백과 끝의 문장부호(. , ! ? ~ …)를 뺀 모양. exact 비교용.
  function exactForm(t) {
    var a = 0, b = t.length;
    while (a < b && isSpace(t.charCodeAt(a))) a++;
    while (b > a && (isSpace(t.charCodeAt(b - 1)) || '.,!?~…'.indexOf(t.charAt(b - 1)) !== -1)) b--;
    return t.substring(a, b);
  }

  // '근로기준법 제23조' → { law: '근로기준법', art: '23' }, '제76조의2' → art '76의2'. 표기가 다르면 null.
  function parseLaw(s) {
    var m = /^(.*?)\s*제\s*(\d+)\s*조(?:\s*의\s*(\d+))?\s*$/.exec(norm(s));
    if (!m) return null;
    return { law: m[1].replace(/\s+/g, ' ').trim(), art: m[2] + (m[3] ? '의' + m[3] : '') };
  }
  // 입력 속 조문 표기들: [{ art, before }]. before 는 그 조문 바로 앞의 글(법 이름 확인용).
  function articlesIn(t) {
    var re = /제\s*(\d+)\s*조(?:\s*의\s*(\d+))?/g, out = [], m;
    while ((m = re.exec(t)) !== null) {
      out.push({ art: m[1] + (m[2] ? '의' + m[2] : ''), before: t.slice(0, m.index).replace(/\s+$/, '').replace(/\s+/g, ' ') });
    }
    return out;
  }
  // 법 이름과 조문이 함께 있으면 그 법의 그 조문, 조문만 있으면 어떤 법이든 그 조문. 제23조의2 는 제23조와 다르다.
  function lawHit(arts, laws) {
    for (var i = 0; i < (laws || []).length; i++) {
      var pl = parseLaw(laws[i]);
      if (!pl) continue;
      for (var k = 0; k < arts.length; k++) {
        if (arts[k].art !== pl.art) continue;
        var b = arts[k].before;
        var named = b.length >= 2 && /[가-힣]법(률)?$|시행령$|시행규칙$/.test(b.slice(-8));
        if (!named || b.slice(-pl.law.length) === pl.law) return true;
      }
    }
    return false;
  }

  // 입력에서 쟁점을 잡는다: 쟁점의 일상어(field)·법률 용어(terms) 중 하나가 일치하면 그 쟁점.
  function detectIssues(text, issues) {
    var t = norm(String(text || '').slice(0, MAX_INPUT));
    var out = [];
    if (!t) return out;
    var whole = exactForm(t);
    var arts = articlesIn(t);
    for (var i = 0; i < issues.length; i++) {
      var ex = issues[i].exact || [];
      var hit = false;
      for (var e = 0; e < ex.length; e++) { if (whole && whole === norm(ex[e])) { hit = true; break; } }
      if (hit) { out.push(issues[i]); continue; }
      if (arts.length && lawHit(arts, issues[i].laws)) { out.push(issues[i]); continue; }
      var list = (issues[i].field || []).concat(issues[i].terms || []);
      for (var j = 0; j < list.length; j++) {
        var ps = pieces(norm(list[j]));
        if (ps.length && matchPieces(t, ps)) { out.push(issues[i]); break; }
      }
    }
    return out;
  }

  function words(text) {
    var seen = {}, out = [];
    var parts = String(text || '').slice(0, MAX_INPUT).split(/\s+/);
    for (var i = 0; i < parts.length && out.length < MAX_WORDS; i++) {
      var w = norm(parts[i]);
      if (w.length >= 2 && !seen[w]) { seen[w] = 1; out.push(w); }
    }
    return out;
  }

  function year(d) { return Number(String(d || '').replace(/\D/g, '').slice(0, 4)) || 0; }
  function dateKey(d) { return Number(String(d || '').replace(/\D/g, '').slice(0, 8)) || 0; }

  // 정렬: 함께 맞힌 쟁점 수 → 쟁점 표현 수 → 본문 표지 → 낱말 → 대법원 → 최신. 점수는 내보내지 않는다.
  // 쟁점 수가 먼저인 까닭: 표현이 많은 쟁점이 함께 잡힌 작은 쟁점을 밀어내지 않게 한다.
  // 본문 표지는 쟁점 수에 세지 않는다. 표지 둘이 요지 일치 하나를 앞지르지 않게 하려는 것이다.
  // 같은 쟁점 수 안에서는 쟁점별로 번갈아 놓는다(takeTurns). 쟁점이 하나면 순서는 그대로다.
  function rank(records, q) {
    q = q || {};
    var issueTerms = [];
    (q.issues || []).forEach(function (is, at) {
      (is.terms || []).forEach(function (x) {
        var ps = pieces(norm(x));
        if (ps.length) issueTerms.push([x, ps, at]);
      });
    });
    var ws = words(q.text);
    var scored = [];
    for (var i = 0; i < records.length; i++) {
      var r = records[i];
      if (q.courtOnly && r.court !== '대법원') continue;
      if (q.sinceYear && year(r.date) < q.sinceYear) continue;
      var hay = norm((r.name || '') + ' ' + (r.text || '') + ' ' + (r.no || ''));
      var matched = [], issueHits = 0, wordHits = 0, tagHits = 0, tagged = [], hitIssues = {}, issuesHit = 0, j;
      var tags = Array.isArray(r.tags) ? r.tags : [];
      for (j = 0; j < issueTerms.length; j++) {
        if (matchPieces(hay, issueTerms[j][1])) {
          issueHits++; matched.push(issueTerms[j][0]);
          if (!hitIssues[issueTerms[j][2]]) { hitIssues[issueTerms[j][2]] = 1; issuesHit++; }
        }
        else if (tags.indexOf(issueTerms[j][0]) !== -1 && tagged.indexOf(issueTerms[j][0]) === -1) {
          tagHits++; tagged.push(issueTerms[j][0]); matched.push(issueTerms[j][0]);
        }
      }
      for (j = 0; j < ws.length; j++) {
        if (hay.indexOf(ws[j]) !== -1) { wordHits++; if (matched.indexOf(ws[j]) === -1) matched.push(ws[j]); }
      }
      if (!issueHits && !wordHits && !tagHits) continue;
      scored.push({ record: r, matched: matched, tagged: tagged,
        k: [issuesHit, issueHits, tagHits, wordHits, r.court === '대법원' ? 1 : 0, dateKey(r.date)], n: i,
        ats: Object.keys(hitIssues).map(Number) });
    }
    scored.sort(function (a, b) {
      for (var x = 0; x < a.k.length; x++) if (a.k[x] !== b.k[x]) return b.k[x] - a.k[x];
      return a.n - b.n;
    });
    return takeTurns(scored).map(function (s) { return { record: s.record, matched: s.matched, tagged: s.tagged }; });
  }

  // 판례가 많은 쟁점이 첫 쪽을 독차지하면 함께 잡힌 작은 쟁점의 판례가 보이지 않는다.
  // 그래서 같은 쟁점 수 안에서 판례를 '맞힌 쟁점 중 가장 작은 쟁점'으로 묶고, 작은 쟁점부터 하나씩 번갈아 놓는다.
  // scored 는 이미 정렬돼 있고, 쟁점을 맞히지 않은 판례는 맨 뒤에 그대로 둔다.
  function takeTurns(scored) {
    var size = {}, out = [], i = 0;
    function smaller(a, b) { return size[a] - size[b] || a - b; }
    scored.forEach(function (s) {
      s.ats.forEach(function (at) { size[at] = (size[at] || 0) + 1; });
    });
    while (i < scored.length && scored[i].k[0]) {
      var level = scored[i].k[0], queues = {}, order = [];
      for (; i < scored.length && scored[i].k[0] === level; i++) {
        var at = scored[i].ats.slice().sort(smaller)[0];
        if (!queues[at]) { queues[at] = []; order.push(at); }
        queues[at].push(scored[i]);
      }
      order.sort(smaller);
      for (var turn = 0; out.length < i; turn++) {
        for (var q = 0; q < order.length; q++) {
          if (queues[order[q]][turn]) out.push(queues[order[q]][turn]);
        }
      }
    }
    return out.concat(scored.slice(i));
  }

  var api = { detectIssues: detectIssues, rank: rank, matchPhrase: matchPhrase };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.PrecSearch = api;
})(typeof window !== 'undefined' ? window : this);
