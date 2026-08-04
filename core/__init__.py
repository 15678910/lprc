"""공용 유틸 — 이 프로젝트는 환경변수·시크릿 로더만 쓴다."""

from .env_loader import load_env, get_secret

__all__ = ["load_env", "get_secret"]
