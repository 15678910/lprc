# 판례 찾기 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 현장 상황을 입력하면 노동 판례를 브라우저 안에서 찾아 주는 `prec.html` 을 만들고, 멈춘 법제처 수집을 되살린다.

**Architecture:** 파이썬 수집기가 법제처에서 판례를 모아 `docs/prec/` 에 공개 JSON 으로 둔다. 화면은 그 JSON 을 받아 입력값을 브라우저 안에서만 대조한다. 현장 말은 용어 사전으로 쟁점에 연결한다.

**Tech Stack:** Python 표준 라이브러리(수집기), 순수 JS(화면), pytest, `node --test`, GitHub Actions.

**Spec:** `.claude/specs/2026-11-05-prec-search-design.md`

## Global Constraints

- 수집기는 표준 라이브러리만. 키는 `LAW_OC` 환경변수로만 읽고 없으면 `RuntimeError`(dev fallback 금지).
- 키 값은 코드·커밋·로그·대화·공개 파일에 넣지 않는다. 법제처 응답의 `판례상세링크`·`결정문상세링크` 는 저장 금지.
- 입력값은 전송·`localStorage`·URL·문서 제목에 넣지 않는다. 외부 자료는 `textContent` 로만 넣는다.
- 승소 가능성·유불리 판단, AI 요약 금지. 화면에 수록 건수·기준일·출처(`법제처 국가법령정보센터`)·한계를 적는다.
- 용어: 측정기, 단체교섭, 단체협약. 인물 중심 표현 금지. 응답·문서는 한글.
- 요청 간격 1.2초 이상. 파이썬은 `encoding='utf-8'`. 긴 스크립트는 파일로 저장 후 실행.
- `docs/prec/index.json` 은 gzip 후 2MB 이하.
- `docs/superpowers/` 에 문서를 두지 않는다(`docs/` 는 공개 폴더).

## Review Focus

1. 실명·회사명이 든 수천 자 붙여넣기: 멈추지 않고, 입력 중 네트워크 요청이 없으며, URL·제목·저장소에 남지 않는다. → Task 5·6
2. 조사 붙은 표현("해고당했어요", "해고를")과 쟁점이 하나도 안 잡히는 입력: 앞은 잡히고, 뒤는 쟁점 고르기로 이어진다. → Task 5
3. 색인 내려받기 실패·느린 회선: 입력을 지우지 않고 오류 문구와 다시 시도를 보여 준다. → Task 6
4. 판결요지가 빈 판례·상세 조회가 없는 판례: 판시사항으로 대체하고, 그것도 없으면 원문 링크만 보여 준다. → Task 2·6
5. 법제처가 빈 목록이나 인증 실패를 주는 날: 기존 데이터를 지우지 않는다(건수가 직전의 90% 미만이면 쓰기 거부). → Task 2

---

### Task 1: 법제처 키 전환과 실패 드러내기

**Files:**
- Create: `law_api.py`, `tests/test_law_api.py`
- Modify: `law_watch.py:32-59,61-76`, `public_servant.py:68,291-295`, `.github/workflows/data.yml`(머리말 시크릿 목록, `public_servant`·`law_watch` 단계 env, '키 불필요' 주석)

**Interfaces:**
- Produces: `law_api.law_oc() -> str`, `law_api.check_auth(data: dict) -> dict`, `law_api.redact(text: str) -> str`, 예외 `law_api.LawAuthError(RuntimeError)`

- [ ] **Step 1: 실패하는 시험 작성** (`tests/test_law_api.py`)

```python
def test_law_oc_requires_env(monkeypatch):
    monkeypatch.delenv("LAW_OC", raising=False)
    with pytest.raises(RuntimeError):
        law_api.law_oc()

def test_check_auth_raises_on_verification_failure():
    with pytest.raises(law_api.LawAuthError):
        law_api.check_auth({"result": "사용자 정보 검증에 실패하였습니다.", "msg": "x"})

def test_check_auth_passes_normal_payload():
    data = {"LawSearch": {"totalCnt": "1"}}
    assert law_api.check_auth(data) is data

def test_redact_removes_key(monkeypatch):
    monkeypatch.setenv("LAW_OC", "abc123")
    assert "abc123" not in law_api.redact("url?OC=abc123&x=1")

def test_law_watch_exits_nonzero_on_auth_failure(monkeypatch, tmp_path):
    monkeypatch.setenv("LAW_OC", "abc123")
    monkeypatch.setattr(law_watch, "OUT", str(tmp_path / "law_watch.json"))
    monkeypatch.setattr(law_watch, "fetch_current", raise_auth_error)
    assert law_watch.main() == 1
    assert not (tmp_path / "law_watch.json").exists()
```

`raise_auth_error` 는 `LawAuthError` 를 던지는 시험 안 보조 함수다.

- [ ] **Step 2: 실행해 실패 확인** — `python -m pytest tests/test_law_api.py -q --tb=line | tail -n 20` → 모듈 없음 오류
- [ ] **Step 3: `law_api.py` 구현, `law_watch.py`·`public_servant.py` 적용.** `law_watch.fetch_current` 는 응답을 `check_auth` 에 통과시키고, `main` 은 `LawAuthError` 면 기존 파일을 건드리지 않고 `1` 을 돌려준다. 다른 일시 실패의 `return 0` 동작은 유지한다. `public_servant._law` 의 `setdefault("OC", "test")` 를 `law_oc()` 로 바꾸고 `check_auth` 를 거친다. `OC=test` 문자열을 저장소 코드에서 없앤다.
- [ ] **Step 4: 시험 통과 확인** — 같은 명령 → 전부 통과
- [ ] **Step 5: 로컬 확인** — `LAW_OC` 를 env 로 주고 `python law_watch.py` → 법령 3종 출력, `docs/law_watch.json` 의 `checked_at` 이 오늘. easylaw 값은 출력하지 않는다.
- [ ] **Step 6: 보안 검토** — 시크릿 처리가 바뀌므로(PART 10) 푸시 전에 `security-reviewer`(opus 지정)에게 "이 변경의 보안 결함을 찾아라"로 맡긴다. 대상: `law_api.py`, `law_watch.py`, `public_servant.py`, `data.yml`. CRITICAL·HIGH 는 고친 뒤 재검토한다.
- [ ] **Step 7: 커밋·푸시** — `git pull --rebase` 후 push
- [ ] **Step 8: Actions 시험** — `gh workflow run data.yml` 후 `gh run watch` 를 백그라운드로 실행. 로그에 `현행 항목` 실패가 없고 `docs/law_watch.json` 이 갱신되면 성공. **결과에 따라 Task 1b 수행 여부가 갈린다.**

### Task 1b: PC 경로 (Task 1 Step 8 이 인증 실패일 때만)

**Files:** Create `.claude/tools/run_law_jobs.ps1`; Modify `health_check.py`(FRESH), `.github/workflows/data.yml`(law_watch 단계 삭제)

- [ ] **Step 1:** 사용자에게 open.law.go.kr API 관리 화면의 IP 설정 확인을 요청한다. 거기서 풀리면 이 Task 를 건너뛴다.
- [ ] **Step 2:** `run_law_jobs.ps1 -Job law|prec` 작성. 사용자 환경변수 `LAW_OC` 를 읽어 수집기 실행 → `git pull --rebase` → 변경분만 커밋·push.
- [ ] **Step 3:** 사용자 승인 후 작업 스케줄러 등록(법령 매일, 판례 주 1회, 놓친 실행 수행). 사용자 환경변수 설정도 승인 대상이다.
- [ ] **Step 4:** FRESH 를 `law_watch.json` 7일로, Task 3 의 판례 기준을 15일로 바꾼다. 수동 1회 실행으로 커밋까지 확인한다.

### Task 2: 수집기 `prec_watch.py`

**Files:** Create `prec_watch.py`, `tests/test_prec_watch.py`

**Interfaces:**
- Consumes: `law_api.law_oc`, `check_auth`, `redact`
- Produces: `docs/prec/meta.json` `{generated_at, total, by_law}`, `docs/prec/index.json` `{records: [{id,no,name,court,date,type,text,laws}]}`, `docs/prec/d/NN.json` `{"<id>": {issue, gist, refs}}`
- 함수: `strip_html(s) -> str`, `to_record(item: dict, detail: dict|None, laws: list[str]) -> dict`, `shard_of(pid: int) -> str`(`"%02d" % (pid % 100)`), `build_outputs(records: list[dict]) -> tuple[dict, dict[str, dict]]`, `assert_no_key(text: str, oc: str) -> None`, `guard_shrink(new_total: int, old_total: int) -> None`, `write_if_changed(path: str, obj) -> bool`

- [ ] **Step 1: 실패하는 시험 작성**

```python
ITEM = {"판례일련번호": "616245", "사건번호": "2023두54914", "사건명": "부당해고구제재심판정취소",
        "법원명": "대법원", "선고일자": "2026.01.29", "판결유형": "판결",
        "판례상세링크": "/DRF/lawService.do?OC=secret123&target=prec&ID=616245"}
DETAIL = {"판시사항": "<br/> [1] 근로자 판단 기준", "판결요지": "", "참조조문": "근로기준법 제2조"}

def test_record_is_allowlisted():
    r = prec_watch.to_record(ITEM, DETAIL, ["근로기준법"])
    assert set(r) == {"id","no","name","court","date","type","issue","gist","refs","laws"}
    assert "secret123" not in json.dumps(r, ensure_ascii=False)

def test_strip_html():
    assert prec_watch.strip_html("<br/> [1] 기준<br/>") == "[1] 기준"

def test_missing_detail_keeps_listing_fields():
    r = prec_watch.to_record(ITEM, None, ["근로기준법"])
    assert r["no"] == "2023두54914" and r["issue"] == "" and r["gist"] == ""

def test_assert_no_key_raises():
    with pytest.raises(RuntimeError):
        prec_watch.assert_no_key('{"x":"OC=secret123"}', "secret123")

def test_guard_shrink_refuses_big_drop():
    with pytest.raises(RuntimeError):
        prec_watch.guard_shrink(800, 1000)
    prec_watch.guard_shrink(950, 1000)
    prec_watch.guard_shrink(10, 0)

def test_write_if_changed_is_idempotent(tmp_path):
    p = str(tmp_path / "a.json")
    assert prec_watch.write_if_changed(p, {"a": 1}) is True
    assert prec_watch.write_if_changed(p, {"a": 1}) is False

def test_build_outputs_splits_shards():
    idx, shards = prec_watch.build_outputs([prec_watch.to_record(ITEM, DETAIL, ["근로기준법"])])
    assert idx["records"][0]["id"] == 616245
    assert "616245" in shards["45"]
```

- [ ] **Step 2: 실행해 실패 확인** — `python -m pytest tests/test_prec_watch.py -q --tb=line | tail -n 20`
- [ ] **Step 3: 함수와 `main` 구현.** `LAWS` 는 설계 측정표의 12개 법(산재보험법 제외)이고, 법마다 표기 변형을 더한다: `노동조합법`, `노동쟁의조정법`, `노동조합및노동관계조정법`, `근로자퇴직급여보장법`, `남녀고용평등법`, `기간제및단시간근로자보호등에관한법률`, `파견근로자보호등에관한법률` 등. 변형별 건수를 로그에 남겨 실제로 늘어나는지 본다. 흐름: 전체 JO 목록을 매번 훑는다(`display=100`, `page`. 약 2분이고, 설계의 `sort=ddes` 증분보다 단순하며 빠진 판례도 다시 잡는다) → 일련번호로 합침 → `docs/prec/d/` 에 없는 일련번호만 상세 조회 → 200건마다 저장(이어 받기). `--limit N` 인자 지원. 키 문자열 검사·`guard_shrink` 는 쓰기 직전에 수행. 인증 실패면 쓰기 없이 종료 코드 1. `index.json` 의 `text` 는 판시사항 + 판결요지 앞부분(상수 `GIST_IN_INDEX`, 시작값 300자). 요지를 빼야 할 때는 `GIST_IN_INDEX = 0` 과 `d/NN.json` 의 `gist` 비우기만으로 끝나야 한다(화면은 판시사항으로 대체).
- [ ] **Step 4: 시험 통과 확인**
- [ ] **Step 5: 작은 실수집** — `python prec_watch.py --limit 30 --out <임시폴더>` → 30건 저장, 산출물에 키 문자열 0건, 재실행 시 쓰기 없음. 표기 변형 건수 로그 확인.
- [ ] **Step 6: 커밋** (`docs/prec/` 시험 산출물은 지우고 코드만)

### Task 3: 첫 수집과 자동화 등록

**Files:** Create `docs/prec/*`; Modify `.github/workflows/data.yml`, `health_check.py:27-32`

- [ ] **Step 1:** `prec_watch.py` 를 백그라운드로 실행(약 2시간). 끊기면 이어서 재실행.
- [ ] **Step 2: 크기 확인** — `gzip -9 < docs/prec/index.json | wc -c` → 2,000,000 이하. 넘으면 `GIST_IN_INDEX` 를 줄이고 색인만 다시 만든다. `meta.json` 의 total·by_law 기록.
- [ ] **Step 3: `data.yml`** — 수동 실행 입력 `cases`(boolean) 를 만들고, `if: github.event.schedule == '0 2 * * 0' || github.event.inputs.cases == 'true'` 인 `Collect labor cases` 단계 추가(`timeout-minutes: 30`, env `LAW_OC`, `PYTHONIOENCODING`, `|| echo`). `GEN` 에 `docs/prec` 추가. 머리말 설명 갱신.
- [ ] **Step 4: `health_check.py`** — FRESH 에 `("prec/meta.json", "generated_at", 8)` 추가, `python health_check.py` 는 Task 7 배포 후 확인.
- [ ] **Step 5: 커밋** (`pull --rebase` 후 push, Actions 수동 실행은 Task 7 에서)

### Task 4: 용어 사전과 시나리오

**Files:** Create `docs/prec/terms.json`, `tests/prec_scenarios.json`, `tests/test_prec_terms.py`

**Interfaces:**
- Produces: `terms.json` `{"issues":[{"id","name","field":[현장 표현],"terms":[법률 용어],"laws":["근로기준법 제23조"]}]}`, `prec_scenarios.json` `[{"text","expect":[id]}]`. id 는 영문 소문자이고 부당해고는 `dismissal` 이다.

- [ ] **Step 1: 실패하는 시험 작성** — 쟁점 25~35개, id 중복 없음, `field` 3개 이상, `terms` 1개 이상, `laws` 항목이 `^.+ 제\d+조(의\d+)?$`, 시나리오 20개 이상이고 `expect` id 가 전부 존재.
- [ ] **Step 2: 실행해 실패 확인**
- [ ] **Step 3: 사전·시나리오 작성** — 설계 '쟁점의 첫 묶음' 전부 포함. 조문은 법제처 원문(`law_api` 키 사용)으로 대조.
- [ ] **Step 4: 시험 통과 확인**
- [ ] **Step 5: 독립 검토** — `critic`(opus 지정)에게 "이 사전과 시나리오의 오류를 찾아라"로 맡긴다. 지적을 원문과 대조해 반영한다(검토자도 틀린다).
- [ ] **Step 6: 커밋**

### Task 5: 검색 엔진 `docs/prec-search.js`

**Files:** Create `docs/prec-search.js`, `tests/prec_search.test.js`

**Interfaces:**
- Consumes: `index.json` 의 `records`, `terms.json`
- Produces: `PrecSearch.detectIssues(text: string, issues: Issue[]) -> Issue[]`, `PrecSearch.rank(records, {issues, text, courtOnly, sinceYear}) -> [{record, matched: string[]}]`. 브라우저는 전역, node 는 `module.exports`.

- [ ] **Step 1: 실패하는 시험 작성** (`node:test`)

```js
test('조사가 붙어도 잡는다', () => assert.deepEqual(ids(detect('어제 해고당했어요')), ['dismissal']));
test('띄어쓰기가 달라도 잡는다', () => assert.deepEqual(ids(detect('내일부터 나오지 말래요')), ['dismissal']));
test('쟁점이 없으면 빈 배열', () => assert.deepEqual(detect('오늘 날씨가 좋네요'), []));
test('정규식 문자에 죽지 않는다', () => assert.doesNotThrow(() => rank(R, {issues: [], text: '(*[+?\\'})));
test('5만 자도 1초 안에', () => { const t0 = Date.now(); rank(R, {issues: I, text: '해고 '.repeat(20000)}); assert.ok(Date.now() - t0 < 1000); });
test('쟁점 일치가 낱말 일치보다 앞선다', ...);
test('같은 조건이면 대법원이 앞선다', ...);
test('같은 법원이면 최신이 앞선다', ...);
test('courtOnly 는 대법원만 남긴다', ...);
test('점수를 결과에 내보내지 않는다', () => assert.equal('score' in rank(R, q)[0], false));
```

위 시험의 `detect`·`rank` 는 시험 안의 작은 사전과 표본을 쓴다. `tests/prec_scenarios.json` 을 실제 `terms.json` 으로 돌려 통과 수를 세는 시험도 넣고, **20개 중 18개 이상**을 단정한다.

- [ ] **Step 2: 실행해 실패 확인** — `node --test tests/prec_search.test.js 2>&1 | tail -n 20`
- [ ] **Step 3: 구현.** 사전 표현을 공백으로 나눠 입력에서 순서대로 찾고, 조각 사이에는 공백만 허용한다(정규식 미사용, 입력 공백은 지우지 않음. 가운뎃점 `·ㆍ・`는 비교 전 제거). 2026-11-05 원장 Ruling 5 로 변경. 낱말은 공백 분리 후 2글자 이상, 앞 50개만 쓴다. 입력은 앞 5,000자만 본다.
- [ ] **Step 4: 시험 통과 확인.** 18개 미달이면 Task 4 사전을 고치고 다시 잰다.
- [ ] **Step 5: 커밋**

### Task 6: 화면 `docs/prec.html`

**Files:** Create `docs/prec.html`(300줄 이하), `docs/prec-ui.js`

**Interfaces:**
- Consumes: `PrecSearch`, `docs/prec/{meta,index,terms}.json`, `docs/prec/d/NN.json`

- [ ] **Step 1: 화면 작성** — 설계 §5 그림대로. 머리띠·메타·`site.css`·`site.js`·`sidenav.js` 포함. 쟁점 칩(× 제거, + 추가), 대법원만·최근 10년 거르기, 요지 펼치기, 원문 링크 `https://www.law.go.kr/LSW/precInfoP.do?precSeq=<id>`, 한계·출처·기준일.
- [ ] **Step 2: 동작 규칙 구현** — JSON 은 첫 검색 때만 받는다. 실패 시 입력을 유지하고 오류 문구와 [다시 시도]. 요지가 비면 판시사항, 그것도 비면 "요지가 없는 판례입니다. 원문을 보세요." 쟁점 0개면 쟁점 목록을 보여 준다. 결과는 20건씩 더 보기.
- [ ] **Step 3: 로컬 확인(8741)** — 시나리오 3개 입력. `read_network_requests` 로 입력 중 요청 0건, 첫 검색 때 `docs/prec/` 만 요청됨을 확인. `location.href`·`document.title`·`localStorage` 에 입력이 없음을 `javascript_tool` 로 확인. 색인 요청 차단 시 오류·다시 시도 동작.
- [ ] **Step 4: 375px 확인** — `document.documentElement.scrollWidth <= 375`, 긴 사건명 넘침 없음.
- [ ] **Step 5: 커밋**

### Task 7: 사이트 연결, 검토, 배포

**Files:** Modify 모든 `docs/*.html` 머리띠(`.grp` 의 원청교섭 가이드 `.sub`), `docs/site.js:39-40`, `docs/index.html`, `docs/guide.html`, `docs/about.html`, `docs/sitemap.xml`, `health_check.py:27`, `CLAUDE.md`, `.claude/HANDOFF.md`

- [ ] **Step 1: 새 페이지 템플릿 ①~⑧ 적용** — 메뉴 이름 `판례 찾기`. 멱등 스크립트로 넣고 건수 assert. `site.js` 를 고치므로 모든 html 의 `?v=` 를 올린다.
- [ ] **Step 2: `about.html`** — 개인정보 표에 "판례 찾기에 입력한 상황 / 저장하지 않음 / 전송 안 함", 출처 표에 법제처 국가법령정보센터(판례·기준일). `health_check.py` PAGES 에 `prec.html`.
- [ ] **Step 3: `CLAUDE.md`** — 자주 발생하는 실수에 `OC=test 막힘`, 자동화 표·시크릿 목록에 `LAW_OC`, 수집기 추가.
- [ ] **Step 4: 전체 시험** — `python -m pytest tests -q --tb=line | tail -n 20`, `node --test tests/ 2>&1 | tail -n 20`
- [ ] **Step 5: 보안 검토** — `security-reviewer`(opus 지정)에게 "이 변경의 보안 결함을 찾아라"로 맡긴다. 대상: `law_api.py`, `prec_watch.py`, `data.yml`, `prec-ui.js`, `docs/prec/`. CRITICAL·HIGH 는 고친 뒤 재검토, MEDIUM 을 미루면 `docs/THREAT_MODEL.md` 에 적는다.
- [ ] **Step 6: 커밋·배포** — `git pull --rebase` 후 push. 배포본 폴링으로 `prec.html` 200 확인. `gh workflow run data.yml -f cases=true` 로 판례 단계 실행 확인(회사 재무는 돌지 않는다).
- [ ] **Step 7: 배포 확인** — `python health_check.py` 문제 0건, 이슈 #2 자동 종료, 배포본에서 시나리오 1개 검색과 375px 확인.
- [ ] **Step 8: `HANDOFF.md` 기록** — 무엇을·왜·다음 할 일(산재·노동위 결정문 2단계) 기록 후 커밋.
