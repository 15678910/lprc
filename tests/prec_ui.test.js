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

test('matchedLine: 일치 낱말 + 쟁점 조문, 중복 제거, 개수 제한', () => {
  const issues = [{ terms: ['부당해고'], laws: ['근로기준법 제23조'] }, { terms: ['수습'], laws: ['x'] }];
  assert.deepEqual(u.matchedLine(['부당해고', '나오지'], issues, 6), ['부당해고', '나오지', '근로기준법 제23조']);
  assert.equal(u.matchedLine(['a', 'b', 'c'], [], 2).length, 2);
});

test('sinceYearFor: 10년 전', () => {
  assert.equal(u.sinceYearFor(new Date('2026-11-05')), 2016);
});
