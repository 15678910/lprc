# -*- coding: utf-8 -*-
"""세션 전수 진단 — 이 프로젝트의 Claude Code 세션 기록(JSONL)에서 반복되는 실패와 사용자 교정을 센다.

왜: 에이전트 개선을 감으로 하지 않고, 실제로 여러 번 겪은 실패를 숫자로 뽑아 CLAUDE.md 의
'자주 발생하는 실수'에 반영하기 위해서다.

읽는 곳: ~/.claude/projects/<이 프로젝트 폴더를 바꾼 이름>/*.jsonl (로컬에만 있음, 저장소에 올리지 않음)
쓰는 곳: .claude/SESSION_AUDIT.md — 분류별 건수와 예시 한 줄만. 명령 원문·토큰·키는 남기지 않는다.

    python .claude/tools/session_audit.py
표준 라이브러리만.
"""
import glob
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime

# 실패 분류 — (이름, 정규식, 대응 규칙). 순서가 우선순위.
RULES = [
    ("셸 heredoc 파싱 실패", r"unexpected EOF while looking for matching|here-document", "긴 스크립트는 Write 도구로 파일에 저장한 뒤 실행"),
    ("푸시 거부(원격이 앞섬)", r"\[rejected\]|fetch first|non-fast-forward", "push 전에 pull --rebase (매일 자동 커밋이 끼어듦)"),
    ("git 자격증명 실패", r"could not read Username|terminal prompts disabled|Authentication failed", "git -c credential.helper= -c \"credential.helper=!gh auth git-credential\" push"),
    ("미커밋 변경으로 pull 실패", r"cannot pull with rebase|You have unstaged changes", "stash → pull --rebase → stash pop, 또는 먼저 커밋"),
    ("요청 과다(429)", r"\b429\b|Too Many Requests", "외부 서버(NORMLEX 등)는 간격을 두고 한 번씩, 또는 브라우저 창으로 한 번 읽기"),
    ("접근 거부(403)", r"\b403\b|Forbidden", "다른 공식 경로(cdn 주소, PDF 다운로드)나 검색으로 원문 대조"),
    ("명령 시간 초과", r"timed out|did not complete within|Timeout", "긴 작업은 run_in_background, 배포 확인은 폴링 루프로"),
    ("편집 대상 문자열 없음", r"String to replace not found|old_string|찾기 실패|!! ", "치환 전 grep 으로 정확한 원문 확인, 스크립트는 건수 assert"),
    ("읽지 않은 파일 편집", r"has not been read|must Read", "편집 전 Read"),
    ("파이썬 문법·인코딩 오류", r"SyntaxError|UnicodeEncodeError|cp949|UnicodeDecodeError", "sys.stdout.reconfigure(encoding='utf-8'), 파일은 encoding='utf-8'"),
    ("단언 실패(중복·누락)", r"AssertionError", "스크립트를 다시 돌리기 전에 이미 적용됐는지 확인(멱등성)"),
    ("DOM 선택자·지연 로딩 오판", r"querySelector|is not a valid selector|Cannot read properties of null|still loading", "지연 카드는 데이터 도착까지 폴링한 뒤 검사"),
    ("텔레그램 발송 실패", r"chat not found|bot is not a member|Unauthorized|error_code", "채널 이름·봇 관리자 여부·토큰 폐기 여부 순서로 확인"),
    ("API 오류(KOSIS 등)", r"\"err\"|오류 ?20|errMsg|서비스 없음", "메타 조회(getMeta)로 itmId·objL 먼저 확인"),
    ("브라우저 패널·탭 상태", r"No preview is open|no longer open|Port \d+ is in use|navigation to .* was denied|ref not found|stale|pinned to a local file|not a valid file path|read_page tree|Failed to fetch|preview pane|Screenshot", "로컬 확인은 launch.json 의 docs(8741) 서버로, 탭 id 는 매번 tabs_context 로"),
    ("PowerShell 문법·형식", r"Unable to find type|At line:\d|ParserError|CommandNotFoundException", "파일·JSON 처리는 PowerShell 대신 Bash + python"),
    ("외부 사이트 가져오기 불가", r"unable to fetch from|Response body not available|MCP error", "다른 언론사 기사·공식 원문으로 같은 사실을 대조"),
    ("세션·사용량 한도", r"session limit|usage limit", "긴 조사는 에이전트에 나눠 맡기고, 중간 결과를 HANDOFF 에 적어 둔다"),
    ("워크플로·리베이스", r"could not find any workflows|workflow .* not found|Could not apply|CONFLICT", "gh workflow run data.yml --repo 15678910/lprc, 충돌 시 원격 자동 커밋을 먼저 받는다"),
    ("경로 오류", r"No such file or directory|not a file or folder inside|cannot find the path", "절대 경로 사용, 다른 저장소는 request_directory 로 먼저 접근 허가"),
    ("도구 미설치", r"not installed|command not found", "PDF 는 pypdf, 표준 라이브러리로 대체"),
    ("사용자·권한 거부", r"doesn't want to proceed|Blocked:|rejected \(eg", "같은 명령 재시도 금지 — 이유를 확인하고 다른 방법"),
    ("파이썬 실행 오류(Traceback)", r"Traceback", "수집 스크립트는 응답 구조를 먼저 찍어 본 뒤 파싱, 이전 산출물이 없을 때도 돌게"),
    ("기타 실패", r".", "—"),
]
# 사용자 교정 신호 — 사용자가 결과를 되돌리거나 고치라고 한 말
CORRECTIONS = [
    ("수정·삭제 요청", r"수정해|삭제해|지워|바꿔|고쳐"),
    ("아직 안 됨", r"아직입니다|아직 안|안 되|안되|안 보|보이지 않"),
    ("혼동·착각", r"혼동|착각|잘못"),
    ("중지", r"중지|멈춰|stop"),
]


def project_dir():
    here = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    key = re.sub(r"[:\\/]", "-", here)
    base = os.path.join(os.path.expanduser("~"), ".claude", "projects")
    for d in glob.glob(os.path.join(base, "*")):
        if os.path.basename(d).lower() == key.lower():
            return d
    return None


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for c in content:
            if isinstance(c, dict):
                if c.get("type") == "text":
                    out.append(c.get("text", ""))
                elif c.get("type") == "tool_result":
                    out.append(text_of(c.get("content")))
        return "\n".join(out)
    return ""


def scrub(s):
    s = re.sub(r"\d{6,}:[A-Za-z0-9_-]{20,}", "<토큰>", s)          # 텔레그램 봇 토큰 모양
    s = re.sub(r"(?i)bearer\s+\S{12,}", "Bearer <숨김>", s)
    s = re.sub(r"\b(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})", "<깃허브토큰>", s)
    s = re.sub(r"\b(AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{30,}|sk-[A-Za-z0-9_-]{20,})", "<키>", s)
    s = re.sub(r"(?i)(key|token|secret|password)=\S+", r"\1=<숨김>", s)
    s = re.sub(r"[A-Za-z0-9_-]{32,}", "<긴문자열>", s)
    return re.sub(r"\s+", " ", s).strip()[:110]


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    d = project_dir()
    if not d:
        print("세션 폴더를 찾지 못했습니다"); return 1
    files = sorted(glob.glob(os.path.join(d, "*.jsonl")))
    tool_use = Counter()
    fails = Counter(); fail_ex = {}
    corr = Counter(); corr_ex = defaultdict(list)
    n_user = 0; first = last = None
    for f in files:
        names = {}
        with open(f, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                ts = o.get("timestamp")
                if ts:
                    first = min(first or ts, ts); last = max(last or ts, ts)
                msg = o.get("message") or {}
                content = msg.get("content")
                if o.get("type") == "assistant" and isinstance(content, list):
                    for c in content:
                        if isinstance(c, dict) and c.get("type") == "tool_use":
                            tool_use[c.get("name", "?")] += 1
                            names[c.get("id")] = c.get("name", "?")
                if o.get("type") == "user":
                    if isinstance(content, list) and any(isinstance(c, dict) and c.get("type") == "tool_result" for c in content):
                        for c in content:
                            if not (isinstance(c, dict) and c.get("type") == "tool_result"):
                                continue
                            t = text_of(c.get("content"))
                            bad = c.get("is_error") or re.search(r"Exit code [1-9]|Traceback|\[ERR\]|<error>", t or "")
                            if not bad:
                                continue
                            for name, rx, _ in RULES:
                                if re.search(rx, t or ""):
                                    fails[name] += 1
                                    fail_ex.setdefault(name, scrub(t))
                                    break
                    else:
                        t = text_of(content)
                        if not t or t.startswith("<") or "tool_result" in t[:40]:
                            continue
                        if t.startswith("This session is being continued") or len(t) > 400:
                            continue   # 세션 요약문·긴 붙여넣기는 교정 신호가 아니다
                        n_user += 1
                        for name, rx in CORRECTIONS:
                            if re.search(rx, t):
                                corr[name] += 1
                                if len(corr_ex[name]) < 3:
                                    corr_ex[name].append(scrub(t))
    rule_fix = {n: fix for n, _, fix in RULES}
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    L = [f"# 세션 전수 진단 — lprc", "",
         f"생성 {now} · 세션 파일 {len(files)}개 · 기간 {str(first)[:10]} ~ {str(last)[:10]} · 사용자 메시지 {n_user}개 · 도구 호출 {sum(tool_use.values())}회",
         "", "`python .claude/tools/session_audit.py` 로 다시 만든다. 명령 원문·토큰은 남기지 않는다(예시는 110자로 자르고 긴 문자열은 가림).", "",
         "## 반복된 실패 (많은 순)", "", "| 분류 | 건수 | 대응 규칙 | 예시 |", "|---|---|---|---|"]
    for name, n in fails.most_common():
        L.append(f"| {name} | {n} | {rule_fix[name]} | {fail_ex[name].replace('|', '/')} |")
    L += ["", "## 사용자 교정 신호", "", "| 신호 | 건수 | 예시 |", "|---|---|---|"]
    for name, n in corr.most_common():
        L.append(f"| {name} | {n} | {' / '.join(x.replace('|', '/') for x in corr_ex[name])} |")
    L += ["", "## 도구 사용", "", " · ".join(f"{k} {v}" for k, v in tool_use.most_common(12)), ""]
    out = os.path.join(os.path.dirname(__file__), "..", "SESSION_AUDIT.md")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main())
