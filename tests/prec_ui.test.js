const test = require('node:test');
const assert = require('node:assert/strict');
const u = require('../docs/prec-ui.js');

test('shardName: 끝 두 자리, 숫자 아니면 null', () => {
  assert.equal(u.shardName(625313), '13');
  assert.equal(u.shardName(100), '00');
  assert.equal(u.shardName(7), '07');
  assert.equal(u.shardName('abc'), null);
  assert.equal(u.shardName(-1), null);
});

test('lawUrl: 숫자 id 만', () => {
  assert.equal(u.lawUrl(625313), 'https://www.law.go.kr/LSW/precInfoP.do?precSeq=625313');
  assert.equal(u.lawUrl('1"><script>'), null);
  assert.equal(u.lawUrl(''), null);
});

test('pickGist: 요지 → 판시사항 → 안내', () => {
  assert.deepEqual(u.pickGist({ gist: ' 요지 ', issue: '판시' }), { text: '요지', kind: 'gist' });
  assert.deepEqual(u.pickGist({ gist: '', issue: '판시' }), { text: '판시', kind: 'issue' });
  assert.equal(u.pickGist({ gist: '', issue: '' }).text, u.NO_GIST);
  assert.equal(u.pickGist(undefined).kind, 'none');
});

test('preview: 길면 자르고 비면 안내', () => {
  assert.equal(u.preview({ text: 'abcdef' }, 3), 'abc…');
  assert.equal(u.preview({ text: '' }, 3), u.NO_GIST);
});

test('matchedLine: 일치 낱말만, 중복 제거, 개수 제한(조문은 따로)', () => {
  const issues = [{ terms: ['부당해고'], laws: ['근로기준법 제23조'] }, { terms: ['수습'], laws: ['x'] }];
  assert.deepEqual(u.matchedLine(['부당해고', '나오지', '부당해고'], issues, 6), ['부당해고', '나오지']);
  assert.equal(u.matchedLine(['a', 'b', 'c'], [], 2).length, 2);
});

test('lawsLine: 일치한 쟁점의 조문만, 낱말이 많아도 잘리지 않는다', () => {
  const issues = [{ terms: ['부당해고'], laws: ['근로기준법 제23조', '근로기준법 제24조'] }, { terms: ['수습'], laws: ['x'] }];
  const many = ['부당해고', 'a', 'b', 'c', 'd', 'e', 'f', 'g'];
  assert.deepEqual(u.lawsLine(many, issues, 3), ['근로기준법 제23조', '근로기준법 제24조']);
  assert.deepEqual(u.lawsLine(['zzz'], issues, 3), []);
  assert.equal(u.lawsLine(['부당해고'], issues, 1).length, 1);
});

test('taggedLine: 표현이 있으면 한 줄, 없으면 빈 문자열', () => {
  assert.equal(u.taggedLine(['직장 내 괴롭힘', '불법파견']), '판결문 본문에 나오는 표현: 직장 내 괴롭힘, 불법파견');
  assert.equal(u.taggedLine([]), '');
  assert.equal(u.taggedLine(undefined), '');
  assert.equal(u.taggedLine([null, '']), '');
});

test('sinceYearFor: 10년 전', () => {
  assert.equal(u.sinceYearFor(new Date('2026-11-05')), 2016);
});

test('prec.html: hidden 속성이 display 규칙에 덮이지 않게 한다', () => {
  const html = require('node:fs').readFileSync(require('node:path').join(__dirname, '../docs/prec.html'), 'utf8');
  assert.match(html, /\[hidden\]\s*\{\s*display:\s*none\s*!important/);
});

test('prec.html: 비콘 끔·CSP·인라인 이벤트 없음', () => {
  const html = require('node:fs').readFileSync(require('node:path').join(__dirname, '../docs/prec.html'), 'utf8');
  assert.match(html, /<html[^>]*\sdata-no-beacon/);
  assert.match(html, /http-equiv="Content-Security-Policy"[^>]*script-src 'self'/);
  assert.ok(html.indexOf('Content-Security-Policy') < html.indexOf('<script'));
  assert.ok(!/\sonsubmit\s*=/i.test(html));
  assert.ok(!/<[^>]+\son[a-z]+\s*=/i.test(html), '인라인 on* 이벤트');
  assert.ok(!/<script(?![^>]*\ssrc=)[^>]*>/i.test(html), '인라인 script');
  assert.match(html, /접속 기록에 남을 수 있습니다/);
});

// ---- 최종 리뷰 수정: I3·I5·M5 ----
test('limitHit: 5천 자에 닿으면 알림', () => {
  assert.equal(u.limitHit(4999, 5000), false);
  assert.equal(u.limitHit(5000, 5000), true);
});

test('timer: 제한 시간이 지나면 abort, 끝나면 타이머를 지운다', () => {
  const log = [];
  const AC = function () { this.signal = { aborted: false }; this.abort = () => { this.signal.aborted = true; log.push('abort'); }; };
  let fn = null;
  const t = u.makeTimeout(60000, AC, (f, ms) => { fn = f; log.push('set' + ms); return 7; }, (id) => log.push('clear' + id));
  assert.equal(t.signal.aborted, false);
  fn();
  assert.equal(t.signal.aborted, true);
  t.done();
  assert.deepEqual(log, ['set60000', 'abort', 'clear7']);
});

test('timer: AbortController 가 없으면 제한 없이 동작', () => {
  const t = u.makeTimeout(1000, undefined, () => 1, () => {});
  assert.equal(t.signal, undefined);
  assert.doesNotThrow(() => t.done());
});

test('화면 문구: 불러오는 중·0건 안내·표시 상수', () => {
  assert.equal(u.LOADING_MSG, '판례 자료를 불러오는 중입니다(처음 한 번만).');
  assert.match(u.EMPTY_MSG, /여기서 못 찾아도 판례가 없다는 뜻은 아닙니다\./);
  assert.equal(u.TIMEOUT_MS, 60000);
});

test('prec.html: 한계 문구와 입력 한도 알림', () => {
  const html = require('node:fs').readFileSync(require('node:path').join(__dirname, '..', 'docs', 'prec.html'), 'utf8');
  assert.ok(!html.includes('띄어쓰기를 없애고'));
  assert.match(html, /노동 법률 13개를 참조조문으로 든 판례만 담았습니다\. 참조조문이 없는 하급심 판결은 빠져 있습니다\./);
  assert.match(html, /반대 취지일 수 있습니다\./);
  assert.match(html, /판결요지\(없으면 판시사항\)의 앞부분/);
  assert.match(html, /id="lim"/);
  assert.match(html, /id="status"[^>]*aria-live="polite"/);
});
