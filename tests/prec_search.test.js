const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { detectIssues, rank } = require('../docs/prec-search.js');

const I = [
  { id: 'dismissal', name: '부당해고', field: ['해고', '잘렸', '나오지 말'], terms: ['부당해고', '해고사유'], laws: [] },
  { id: 'wage', name: '임금', field: ['월급', '임금'], terms: ['통상임금'], laws: [] },
];
const R = [
  { id: 1, no: 'a', name: '임금청구', court: '서울고등법원', date: '2020.01.01', type: '판결', text: '통상임금 해당 여부', laws: [] },
  { id: 2, no: 'b', name: '부당해고구제', court: '대법원', date: '2015.05.05', type: '판결', text: '부당해고 정당한 이유', laws: [] },
  { id: 3, no: 'c', name: '부당해고구제', court: '대법원', date: '2022.05.05', type: '판결', text: '부당해고 정당한 이유', laws: [] },
  { id: 4, no: 'd', name: '부당해고구제', court: '서울고등법원', date: '2023.05.05', type: '판결', text: '부당해고 정당한 이유', laws: [] },
  { id: 5, no: 'e', name: '기타', court: '대법원', date: '2024.01.01', type: '판결', text: '근로자 해고 낱말만 있음', laws: [] },
];
const detect = (t) => detectIssues(t, I);
const ids = (a) => a.map((x) => x.id);

test('조사가 붙어도 잡는다', () => assert.deepEqual(ids(detect('어제 해고당했어요')), ['dismissal']));
test('띄어쓰기가 달라도 잡는다', () => assert.deepEqual(ids(detect('내일부터 나오지 말래요')), ['dismissal']));
test('쟁점이 없으면 빈 배열', () => assert.deepEqual(detect('오늘 날씨가 좋네요'), []));
test('정규식 문자에 죽지 않는다', () => assert.doesNotThrow(() => rank(R, { issues: [], text: '(*[+?\\' })));
test('5만 자도 1초 안에', () => {
  const t0 = Date.now();
  rank(R, { issues: I, text: '해고 '.repeat(20000) });
  assert.ok(Date.now() - t0 < 1000);
});
test('쟁점 일치가 낱말 일치보다 앞선다', () => {
  const out = rank(R, { issues: [I[0]], text: '근로자 낱말만' });
  assert.equal(out[0].record.id, 3);
  assert.ok(out.findIndex((x) => x.record.id === 5) > out.findIndex((x) => x.record.id === 2));
});
test('같은 조건이면 대법원이 앞선다', () => {
  const out = rank(R.filter((r) => r.id === 3 || r.id === 4), { issues: [I[0]], text: '' });
  assert.deepEqual(out.map((x) => x.record.id), [3, 4]);
});
test('같은 법원이면 최신이 앞선다', () => {
  const out = rank(R.filter((r) => r.id === 2 || r.id === 3), { issues: [I[0]], text: '' });
  assert.deepEqual(out.map((x) => x.record.id), [3, 2]);
});
test('courtOnly 는 대법원만 남긴다', () => {
  const out = rank(R, { issues: [I[0]], text: '', courtOnly: true });
  assert.ok(out.length > 0 && out.every((x) => x.record.court === '대법원'));
});
test('sinceYear 는 그 해 이후만 남긴다', () => {
  const out = rank(R, { issues: [I[0]], text: '', sinceYear: 2022 });
  assert.ok(out.length > 0 && out.every((x) => Number(x.record.date.slice(0, 4)) >= 2022));
});
test('점수를 결과에 내보내지 않는다', () => {
  const out = rank(R, { issues: [I[0]], text: '해고' });
  assert.equal('score' in out[0], false);
  assert.ok(Array.isArray(out[0].matched));
});
test('일치가 전혀 없으면 결과도 없다', () => assert.deepEqual(rank(R, { issues: [], text: '전혀무관' }), []));

test('시나리오 90% 이상이 기대 쟁점을 잡는다', () => {
  const terms = JSON.parse(fs.readFileSync(path.join(__dirname, '../docs/prec/terms.json'), 'utf8')).issues;
  const sc = JSON.parse(fs.readFileSync(path.join(__dirname, 'prec_scenarios.json'), 'utf8'));
  const fails = [];
  let ok = 0;
  for (const s of sc) {
    const got = ids(detectIssues(s.text, terms));
    if (s.expect.every((e) => got.includes(e))) ok++;
    else fails.push(`${s.text} | 기대 ${s.expect} | 실제 ${got}`);
  }
  const need = Math.ceil(sc.length * 0.9);
  assert.ok(ok >= need, `${ok}/${sc.length} (필요 ${need})\n${fails.join('\n')}`);
});
