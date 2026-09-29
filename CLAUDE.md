# lprc — 모두를 위한 단체교섭 · 에이전트 지침

https://단체교섭.kr (퓨니코드 `xn--9d0b29hf1nhhl.kr`) · GitHub Pages(`master` 의 `docs/`) · 저장소 github.com/15678910/lprc

이 파일은 **짧게 유지하는 규칙집**이다. 무엇을 언제 왜 했는지는 `.claude/HANDOFF.md`(맨 앞 '먼저 볼 것' 표부터)에 있다.
세션을 시작하면 이 파일 → HANDOFF 머리말 → `git log --oneline -10` 순서로 읽는다.

## 원칙 (사이트 전체)

- **모든 응답은 한글.** 전문 용어는 풀어서 쓴다.
- 데이터 페이지(측정기·원청교섭 가이드·현장과 ILO 기준)는 **어느 쪽 주장도 대변하지 않는다.** 한계를 화면에 적고, 모든 숫자에 출처·기준 시점.
- **과장하면 반박당한다.** 인용 수치는 공식 자료와 대조하고, 다르면 다르다고 적는다.
- 수집기는 **표준 라이브러리만**. 키·토큰은 GitHub Secrets 에만 — 코드·커밋·대화에 넣지 않는다.

## 사용자 결정 — 되돌리지 말 것

| 결정 | 내용 |
|---|---|
| 용어 | '계산기' → **측정기**, '임금 교섭' → **단체교섭**, '임금단협' → **단체협약** |
| 인물 중심 금지 | 특정 인물·단체를 앞세운 문구·경고 상자 금지. '현장의 문제 / 제시된 대안 / 현장에서 제기된 수치' 로 쓴다 |
| 전략 공개 | `strategy.html` 은 목표가 있는 전략안이지만 **공개**(같은 설계도를 보면 교섭이 짧아진다). 상대의 걱정·설계 보완을 같은 줄에 |
| 수집 정책 | robots.txt **기본 전부 거부** + 검색엔진(Yeti·Googlebot·Bingbot·Daumoa)·링크 미리보기 봇만 허용. noindex 는 없음 |
| nav | 9칸 순서 고정: 🏠 · 📖 소개 · 🧮 측정기 · ⚖️ 원청교섭 가이드 · 📰 노동뉴스 · 🌐 현장과 ILO 기준 · 🧭 전략과 대안 · 🤖 AI 시대의 노동 · 📋 출처 · 면책 |
| 조합원 전용 | 요구안·수용선·실태 원자료는 `../lprc-members`(git 아님). 공개 저장소에 넣지 않는다 |

## 수정 금지 영역

- `docs/CNAME` — 지우면 도메인 연결이 풀린다.
- `docs/naver9dcac302ef4dfbef41ea050978e951ed.html` 과 `index.html` 의 `naver-site-verification` meta — 네이버 서치어드바이저 소유확인. 지우면 인증이 풀린다.
- 저장소 루트의 **PDF**(법령·자료집 원문) — 커밋 금지.
- 가비아 DNS 의 A 4줄·CNAME(www)·TXT(`_github-pages-challenge-15678910`) — 지우면 연결·소유 인증이 풀린다.
- `law_watch.py` 의 `BASELINE` — labor.html 본문을 새 법령에 맞춰 고칠 때만 함께 올린다.
- 다른 저장소(hybrid-jury-system 등)의 `firebase deploy` — 그 저장소 규칙상 사용자 승인 필요.

## 자주 발생하는 실수 (세션 전수 진단 기반 — `.claude/tools/session_audit.py`, 2026-09-29 기준 세션 4개·도구 호출 1,932회)

| 실수 | 건수 | 규칙 |
|---|---|---|
| 브라우저 탭 상태 착오(탭 닫힘·포트 점유·stale ref) | 12 | 로컬 확인은 `.claude/launch.json` 의 `docs`(8741) 서버. 탭 id 는 매번 확인 |
| 인코딩·JS 문법 | 9 | 파이썬은 `sys.stdout.reconfigure(encoding='utf-8')`, 파일은 `encoding='utf-8'`. 콘솔 cp949 |
| 시간 초과 | 8 | 긴 작업은 백그라운드, 배포 확인은 폴링 루프 |
| 셸 heredoc 파싱 실패 | 6 | **긴 스크립트·긴 HTML 은 Write 도구로 파일 저장 후 실행.** 여러 줄 문자열은 셸로 넘기지 않는다 |
| 경로 오류 | 6 | 절대 경로. 다른 저장소는 먼저 접근 허가 |
| 지연 로딩 카드 오판(⑩⑪⑫⑬) | 5 | 데이터가 도착할 때까지 폴링한 뒤 DOM 검사 |
| 스크립트 재실행으로 중복 삽입 | 1 | 치환 스크립트는 멱등하게(이미 있으면 건너뜀), 건수 assert |
| 푸시 실패 | 4 | 매일 자동 커밋이 끼어든다 → `pull --rebase` 후 push. 자격증명 오류면 `git -c credential.helper= -c "credential.helper=!gh auth git-credential" push` |
| 외부 서버 429·403 (NORMLEX·언론사) | 5 | 연속 요청 금지. 브라우저 창으로 한 번 읽거나 다른 공식 경로로 대조 |
| 조용한 실패 | — | 수집기가 실패해도 exit 0 으로 넘어가는 단계가 있다(2026-09-28 law_watch). **건강 검진이 잡는다** |

## 작업 템플릿

**새 페이지를 더할 때** — ① nav 9곳(모든 html) ② 홈 카드(`index.html`) ③ `guide.html` 사이트 구성 표(#map)·질문 표 ④ `docs/sitemap.xml` 한 줄 ⑤ `<head>` 메타 블록(description·canonical·og) ⑥ `health_check.py` 의 PAGES ⑦ `about.html` 출처 표(데이터가 있으면) ⑧ `sidenav.js` 로드.

**새 수집기를 더할 때** — 표준 라이브러리, 실패 시 기존 파일 보존, 산출물에 `generated_at`, `data.yml` 단계 추가(`|| echo` 로 전체를 멈추지 않게), `health_check.py` 의 FRESH 에 등록, `about.html` 출처 표.

**사실 페이지(법·통계·국제기준)를 쓸 때** — 조문은 국가법령정보센터 원문(DRF API), 해외 법은 원문 사이트로 확인 → 독립 검토 에이전트(critic)에게 "문제를 찾아라"로 검토 → 원자료로 대조한 뒤 반영(검토자도 틀린다).

## 배포 전 체크리스트

1. 로컬 서버(8741)에서 화면 확인 — 목차 링크(`#id`) 깨짐 없음, 휴대폰 너비(375px) 가로 넘침 없음.
2. 사실 페이지면 독립 검토를 거쳤는가.
3. `pull --rebase` → push → 배포본을 폴링으로 확인(GitHub Pages 반영 1~3분).
4. 필요하면 `python health_check.py` — 배포본 전체 점검.
5. HANDOFF.md 에 무엇을·왜·다음 할 일을 적는다.

## 자동화 (무중단)

| 무엇 | 언제 | 실패하면 |
|---|---|---|
| `data.yml` 데이터 갱신 | 매일 KST 10:00 예약(실제 시작은 몇 시간 늦기도 함), 일요일 회사 재무 | `data-fail` 라벨 이슈 자동 생성 |
| `health.yml` 건강 검진 | 매일 KST 13:30 | `health` 라벨 이슈 생성·댓글, 정상이 되면 자동 종료 |
| 텔레그램 `@labornews_lprc` | 데이터 갱신 안에서 | 로그에 봇 이름·오류 이유 |

## 도구

- `python .claude/tools/session_audit.py` — 세션 기록 전수 진단 → `.claude/SESSION_AUDIT.md`(로컬 전용, gitignore). 실수 표를 갱신할 때.
- `python health_check.py` — 배포된 사이트 점검(페이지·데이터 신선도·인증서·robots·sitemap).
