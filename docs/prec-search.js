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

  // 입력에서 쟁점을 잡는다: 쟁점의 일상어(field)·법률 용어(terms) 중 하나가 일치하면 그 쟁점.
  function detectIssues(text, issues) {
    var t = norm(String(text || '').slice(0, MAX_INPUT));
    var out = [];
    if (!t) return out;
    for (var i = 0; i < issues.length; i++) {
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

  // 정렬: 쟁점 일치 → 낱말 일치 → 대법원 → 최신. 점수는 내보내지 않는다.
  function rank(records, q) {
    q = q || {};
    var issueTerms = [];
    (q.issues || []).forEach(function (is) {
      (is.terms || []).forEach(function (x) {
        var ps = pieces(norm(x));
        if (ps.length) issueTerms.push([x, ps]);
      });
    });
    var ws = words(q.text);
    var scored = [];
    for (var i = 0; i < records.length; i++) {
      var r = records[i];
      if (q.courtOnly && r.court !== '대법원') continue;
      if (q.sinceYear && year(r.date) < q.sinceYear) continue;
      var hay = norm((r.name || '') + ' ' + (r.text || ''));
      var matched = [], issueHits = 0, wordHits = 0, j;
      for (j = 0; j < issueTerms.length; j++) {
        if (matchPieces(hay, issueTerms[j][1])) { issueHits++; matched.push(issueTerms[j][0]); }
      }
      for (j = 0; j < ws.length; j++) {
        if (hay.indexOf(ws[j]) !== -1) { wordHits++; if (matched.indexOf(ws[j]) === -1) matched.push(ws[j]); }
      }
      if (!issueHits && !wordHits) continue;
      scored.push({ record: r, matched: matched, k: [issueHits, wordHits, r.court === '대법원' ? 1 : 0, dateKey(r.date)], n: i });
    }
    scored.sort(function (a, b) {
      for (var x = 0; x < 4; x++) if (a.k[x] !== b.k[x]) return b.k[x] - a.k[x];
      return a.n - b.n;
    });
    return scored.map(function (s) { return { record: s.record, matched: s.matched }; });
  }

  var api = { detectIssues: detectIssues, rank: rank, matchPhrase: matchPhrase };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.PrecSearch = api;
})(typeof window !== 'undefined' ? window : this);
