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
// ---- 판결문 본문 표지(tags) ----
const H = { id: 'harass', name: '직장 내 괴롭힘', field: ['괴롭'], terms: ['직장 내 괴롭힘'], laws: [] };
const T1 = { id: 11, no: 't1', name: '손해배상', court: '대법원', date: '2024.01.01', type: '판결', text: '손해배상 청구', tags: ['직장 내 괴롭힘'], laws: [] };
const T2 = { id: 12, no: 't2', name: '징계', court: '서울고등법원', date: '2020.01.01', type: '판결', text: '직장 내 괴롭힘 행위의 징계', laws: [] };
test('표지만 있는 판례도 잡히고 tagged 에 표현이 담긴다', () => {
  const out = rank([T1], { issues: [H], text: '' });
  assert.equal(out.length, 1);
  assert.deepEqual(out[0].tagged, ['직장 내 괴롭힘']);
  assert.deepEqual(out[0].matched, ['직장 내 괴롭힘']);
});
test('요지 일치 판례가 표지만 있는 판례보다 앞선다(대법원·최신이어도)', () => {
  const out = rank([T1, T2], { issues: [H], text: '' });
  assert.deepEqual(out.map((x) => x.record.id), [12, 11]);
  assert.deepEqual(out[0].tagged, []);
});
test('tags 없는 레코드는 오류 없이 동작', () => {
  assert.doesNotThrow(() => rank(R, { issues: [H], text: '해고' }));
  assert.equal(rank([T2], { issues: [H] })[0].tagged.length, 0);
});
test('쟁점 없이 낱말만 넣으면 표지로 잡히지 않는다', () => {
  assert.deepEqual(rank([T1], { issues: [], text: '직장 내 괴롭힘' }), []);
});
test('다른 쟁점의 표현은 표지로 세지 않는다', () => {
  assert.deepEqual(rank([T1], { issues: [I[0]], text: '' }), []);
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

test('시나리오: 기대 쟁점 90% 이상 감지, 금지 쟁점 0건, 함정 문장 20건 이상', () => {
  const terms = JSON.parse(fs.readFileSync(path.join(__dirname, '../docs/prec/terms.json'), 'utf8')).issues;
  const sc = JSON.parse(fs.readFileSync(path.join(__dirname, 'prec_scenarios.json'), 'utf8'));
  const missed = [], violated = [];
  let pos = 0, ok = 0, traps = 0;
  for (const s of sc) {
    const got = ids(detectIssues(s.text, terms));
    if (s.expect && s.expect.length) {
      pos++;
      if (s.expect.every((e) => got.includes(e))) ok++;
      else missed.push(`${s.text} | 기대 ${s.expect} | 실제 ${got}`);
    } else if (s.forbid && s.forbid.length) traps++;
    const bad = (s.forbid || []).filter((f) => got.includes(f));
    if (bad.length) violated.push(`${s.text} | 금지 ${bad}`);
  }
  const need = Math.ceil(pos * 0.9);
  assert.ok(ok >= need, '기대 ' + ok + '/' + pos + ' (필요 ' + need + ')\n' + missed.join('\n'));
  assert.equal(violated.length, 0, '금지 쟁점이 잡힌 문장:\n' + violated.join('\n'));
  assert.ok(traps >= 20, `함정 문장 ${traps}건 (필요 20)`);
});

test('시나리오: 문장마다 종류가 분명하다(expect / forbid / none:true 중 하나)', () => {
  const sc = JSON.parse(fs.readFileSync(path.join(__dirname, 'prec_scenarios.json'), 'utf8'));
  const bad = sc.filter((s) => {
    const e = (s.expect || []).length > 0, f = (s.forbid || []).length > 0, n = s.none === true;
    return n ? (e || f) : !(e || f);
  });
  assert.equal(bad.length, 0, 'expect·forbid 가 모두 비었는데 none:true 가 아니거나, none:true 인데 expect·forbid 가 있는 문장:\n' + bad.map((s) => s.text).join('\n'));
});

test('시나리오: 쟁점 없는 문장(none:true)에 칩이 붙는 비율 10% 이하(최대 3건)', () => {
  const terms = JSON.parse(fs.readFileSync(path.join(__dirname, '../docs/prec/terms.json'), 'utf8')).issues;
  const sc = JSON.parse(fs.readFileSync(path.join(__dirname, 'prec_scenarios.json'), 'utf8'));
  const none = sc.filter((s) => s.none === true);
  const noisy = none.filter((s) => detectIssues(s.text, terms).length > 0);
  assert.ok(none.length >= 20, `쟁점 없는 문장 ${none.length}건 (필요 20)`);
  const limit = Math.min(Math.floor(none.length * 0.1), 3);
  assert.ok(noisy.length <= limit, `칩이 붙은 쟁점 없는 문장 ${noisy.length}/${none.length} (허용 ${limit})\n` +
    noisy.map((s) => s.text + ' | ' + ids(detectIssues(s.text, terms))).join('\n'));
});

const { matchPhrase } = require('../docs/prec-search.js');
test('어절 경계를 넘는 오탐은 일치하지 않는다', () => {
  assert.equal(matchPhrase('대해 고용', '해고'), false);
  assert.equal(matchPhrase('협력업체 불법', '체불'), false);
  assert.equal(matchPhrase('이전 보다', '전보'), false);
  assert.equal(matchPhrase('일부 도급', '부도'), false);
  assert.equal(matchPhrase('부산 재직', '산재'), false);
  assert.equal(matchPhrase('연차 별도', '차별'), false);
});
test('조각 사이 공백은 있어도 없어도 맞는다', () => {
  assert.equal(matchPhrase('부당해고', '부당 해고'), true);
  assert.equal(matchPhrase('부당 해고', '부당 해고'), true);
  assert.equal(matchPhrase('부당  해고', '부당 해고'), true);
  assert.equal(matchPhrase('부당\n해고', '부당 해고'), true);
  assert.equal(matchPhrase('부당한 해고', '부당 해고'), false);
});
test('첫 조각이 여러 곳이면 모두 시도한다', () => {
  assert.equal(matchPhrase('해고는 안 됐고 해고 통보를', '해고 통보'), true);
});
test('가운뎃점은 양쪽에서 무시한다', () => {
  assert.equal(matchPhrase('일·가정 양립', '일ㆍ가정'), true);
  assert.equal(matchPhrase('일ㆍ가정 양립', '일·가정'), true);
  assert.equal(matchPhrase('일가정', '일・가정'), true);
});
test('빈 표현은 false', () => { assert.equal(matchPhrase('abc', ''), false); assert.equal(matchPhrase('abc', '  '), false); });
test('긴 본문에서도 빠르다', () => {
  const t0 = Date.now();
  matchPhrase('해고 '.repeat(100000) + '끝', '해고 통보');
  assert.ok(Date.now() - t0 < 1000);
});

test('낱말 하나만 입력해도 쟁점을 잡는다(허용 오차 없음)', () => {
  const terms = JSON.parse(fs.readFileSync(path.join(__dirname, '../docs/prec/terms.json'), 'utf8')).issues;
  const kw = JSON.parse(fs.readFileSync(path.join(__dirname, 'prec_keywords.json'), 'utf8'));
  assert.ok(kw.length >= 50, `낱말 ${kw.length}건`);
  const bad = [];
  for (const k of kw) {
    const got = ids(detectIssues(k.word, terms));
    const miss = k.expect.filter((e) => !got.includes(e));
    if (miss.length) bad.push(`${k.word} | 기대 ${k.expect} | 실제 ${got}`);
  }
  assert.equal(bad.length, 0, '쟁점을 못 잡은 낱말:\n' + bad.join('\n'));
});

test('exact: 입력 전체가 같을 때만 잡는다', () => {
  const X = [{ id: 'transfer', name: 't', field: [], terms: [], exact: ['전보'] }, { id: 'probation', name: 'p', field: [], terms: [], exact: ['수습'] }, { id: 'noexact', name: 'n', field: ['해고'], terms: [] }];
  const d = (t) => ids(detectIssues(t, X));
  assert.deepEqual(d('전보'), ['transfer']);
  assert.deepEqual(d('전보다'), []);
  assert.deepEqual(d('수습?'), ['probation']);
  assert.deepEqual(d('  수습 … '), ['probation']);
  assert.deepEqual(d('수습하기'), []);
  assert.deepEqual(d('해고'), ['noexact']);
});

// ---- 최종 리뷰 수정: I1 정렬, I6 번호 검색 ----
test('I1: 표지만 있는 판례가 낱말만 맞은 판례보다 앞선다(입력에 흔한 낱말이 있어도)', () => {
  const W = { id: 21, no: 'w', name: '직장폐쇄 기간 중 임금', court: '서울고등법원', date: '1991.01.01', type: '판결', text: '직장폐쇄 기간 중 임금 지급 의무', laws: [] };
  const out = rank([W, T1], { issues: [H], text: '직장 내 괴롭힘을 당했어요' });
  assert.deepEqual(out.map((x) => x.record.id), [11, 21]);
});
test('I1: 요지 일치는 여전히 표지보다 앞선다(입력 낱말이 있어도)', () => {
  const out = rank([T1, T2], { issues: [H], text: '직장 내 괴롭힘을 당했어요' });
  assert.deepEqual(out.map((x) => x.record.id), [12, 11]);
});
const L = [
  { id: 'dis', name: '해고', field: [], terms: ['부당해고'], laws: ['근로기준법 제23조'] },
  { id: 'wage', name: '임금', field: [], terms: ['통상임금'], laws: ['근로기준법 제2조', '최저임금법 제5조'] },
  { id: 'mat', name: '출산', field: [], terms: ['출산휴가'], laws: ['근로기준법 제76조의2', '남녀고용평등과 일ㆍ가정 양립 지원에 관한 법률 제23조의2'] },
];
const lid = (t) => detectIssues(t, L).map((x) => x.id);
test('I6: 사건번호로 찾는다', () => {
  const rec = { id: 31, no: '2023두54914', name: '부당해고구제', court: '대법원', date: '2024.01.01', text: '', laws: [] };
  assert.equal(rank([rec], { issues: [], text: '2023두54914' }).length, 1);
});
test('I6: 법 이름과 조문이 함께 있으면 그 법의 그 조문', () => {
  assert.deepEqual(lid('근로기준법 제23조 위반인가요'), ['dis']);
  assert.deepEqual(lid('최저임금법 제23조'), []);
  assert.deepEqual(lid('최저임금법 제5조'), ['wage']);
  assert.deepEqual(lid('근로기준법 제5조'), []);
});
test('I6: 조문만 있으면 어떤 법이든 그 조문', () => {
  assert.deepEqual(lid('제23조가 궁금합니다'), ['dis']);
  assert.deepEqual(lid('제5조'), ['wage']);
});
test('I6: 제23조의2 는 제23조와 다르고, 제2조는 제23조에 걸리지 않는다', () => {
  assert.deepEqual(lid('제23조의2'), ['mat']);
  assert.deepEqual(lid('제2조'), ['wage']);
  assert.deepEqual(lid('제76조의2'), ['mat']);
  assert.deepEqual(lid('제76조'), []);
});
test('I6: 조문이 없는 일반 문장의 감지는 그대로', () => {
  assert.deepEqual(lid('부당해고 당했어요'), ['dis']);
  assert.deepEqual(lid('오늘 날씨'), []);
});
