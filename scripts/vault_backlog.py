#!/usr/bin/env python3
"""볼트 백로그 — 무인 실행이 남긴 「사람 몫」 목록의 유일한 정의.

**왜 파일 하나인가**: 전에는 그날 일지의 「볼트」 섹션에 적었다. 두 문제가 있었다 —
① 일지가 기계 줄로 지저분해졌고 ② 세션 시작 훅이 **오늘 일지만** 읽어서 어제 이후에
쌓인 항목이 영영 안 올라왔다(폐지 시점의 실볼트에 16건이 그렇게 묻혀 있었다).
목록을 날짜에서 떼어 한 곳에 두면 둘 다 사라진다.

**형식**: `- [ ] <종류>(YYYY-MM-DD): <한 줄 요약>` — 종류는 `ingest` · `lint`.
자동화를 더 붙이면 같은 형식으로 종류를 늘린다. 줄에 날짜를 박는 이유는
lint-freshness 가 「날짜 없는 휘발성 주장」으로 되잡는 루프를 막기 위해서다.

**처리한 줄은 지운다.** `[x]` 로 남기지 않는다 — 이력은 `log.md` 가 갖고, 이 파일은
"지금 사람이 할 것"만 담는 짧은 목록으로 유지한다 (CLAUDE.md: 사람이 할 게 없으면 침묵).

이 모듈이 경로·형식·중복 판정을 전부 갖는다 — 훅·lint_morning·ingest 프롬프트가
각자 정규식을 두면 한쪽만 바뀌고 낡는다(개념: 스키마 이중 정의).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

VAULT = Path(
    os.environ.get("VAULT_PATH") or Path(__file__).resolve().parent.parent
).expanduser()
BACKLOG = VAULT / "볼트-백로그.md"

OPEN = re.compile(r"^- \[ \] (.+)$", re.M)
HEADER = """# 볼트 백로그

무인 ingest(08:00) · 무인 점검(08:30) 이
**자기 권한 밖이라 남긴 사람 몫**.
세션 시작 훅(`scripts/vault_backlog_hook.py`)이 이 목록을 올리고 처리할지 묻는다 —
**보고만 하고, 실행은 사람이 승인한 뒤 대화형으로**(wiki-ingest · wiki-lint).
무인이 기존 페이지를 안 고친다는 규약 §6.2 · §8.1 을 우회하지 않기 위해서다.

형식: `- [ ] <종류>(YYYY-MM-DD): <한 줄 요약>` — 종류는 `ingest` · `lint`.
상세는 `log.md` 에 두고 여기엔 **행동이 필요한 것만 한 줄**.
**처리한 줄은 지운다** (`[x]` 로 남기지 않는다 — 이력은 `log.md`).
"""


def _read() -> str:
    if not BACKLOG.is_file():
        return HEADER
    return BACKLOG.read_text(encoding="utf-8")


def open_items() -> list[str]:
    """열린 항목의 본문(체크박스 접두 제외). 파일이 없으면 빈 목록."""
    return [m.strip() for m in OPEN.findall(_read())]


def has(text: str) -> bool:
    """같은 발견이 이미 올라와 있는가 — 요약의 앞부분(`—` 앞)으로 대조한다.

    lint 는 매일 같은 검사를 돌리므로 같은 발견이 반복 제출된다. 전문 일치로 보면
    날짜만 다른 중복이 매일 쌓인다."""
    key = text.split(" — ")[0].strip()
    return any(key in item for item in open_items())


def add(text: str) -> bool:
    """항목 한 줄 추가. 이미 같은 발견이 있으면 아무것도 하지 않고 False."""
    if has(text):
        return False
    body = _read().rstrip("\n")
    BACKLOG.write_text(body + f"\n\n- [ ] {text}\n", encoding="utf-8")
    return True


def remove(needle: str) -> int:
    """`needle` 이 들어간 열린 항목을 지운다 (처리 완료). 지운 개수를 돌려준다."""
    text = _read()
    kept, removed = [], 0
    for line in text.split("\n"):
        if line.strip().startswith("- [ ]") and needle in line:
            removed += 1
            continue
        kept.append(line)
    if removed:
        BACKLOG.write_text("\n".join(kept), encoding="utf-8")
    return removed


if __name__ == "__main__":  # 눈으로 확인용
    items = open_items()
    print(f"{BACKLOG} — 열린 항목 {len(items)}건")
    for i in items:
        print(f"  - {i}")
