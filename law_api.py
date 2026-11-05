# -*- coding: utf-8 -*-
"""법제처 DRF(국가법령정보센터 Open API) 공통 도우미 — 표준 라이브러리만.

키(OC)는 환경변수 LAW_OC 에서만 읽는다(GitHub Secrets). 코드·로그·커밋에 넣지 않는다.
공유 계정 'test' 가 막혀 수집기가 조용히 멈춘 적이 있어(2026-11), 인증 실패는
응답 본문의 'result' 문구로 알아채 예외로 올린다 — 조용한 실패를 없애는 것이 목적이다.
"""
import os


class LawAuthError(RuntimeError):
    """법제처가 키를 거부했다(사용자 정보 검증 실패 등)."""


def law_oc():
    """환경변수 LAW_OC 를 돌려준다. 없으면 바로 멈춘다(대체값 없음)."""
    oc = os.environ.get("LAW_OC", "").strip()
    if not oc:
        raise RuntimeError("환경변수 LAW_OC 가 없다 — 법제처 OC 키를 GitHub Secrets/환경변수로 준다")
    return oc


def check_auth(data):
    """응답이 인증 실패면 LawAuthError, 아니면 data 를 그대로 돌려준다."""
    if isinstance(data, dict):
        result = data.get("result")
        if isinstance(result, str) and ("검증" in result or "실패" in result):
            raise LawAuthError("%s %s" % (result, data.get("msg", "")))
    return data


def redact(text):
    """문자열 안의 키 값을 가린다(예외 메시지·로그용)."""
    oc = os.environ.get("LAW_OC", "").strip()
    if oc:
        text = text.replace(oc, "***")
    return text
