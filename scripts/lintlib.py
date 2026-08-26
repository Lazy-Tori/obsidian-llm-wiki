#!/usr/bin/env python3
"""lint 스크립트 공용 헬퍼. 검사기가 아니라 부품이므로 `lint-*.py` 글롭에 안 걸린다.

담는 것은 둘뿐이다:
  - `strip_code()` : 코드 블록·인라인 코드 제거. 링크·파일명을 세는 검사가 전부 거친다
  - `emit()`       : `--json` 출력 형식 통일

⚠️ **왜 모았나**: 코드 제거 정규식이 lint-links·lint-lessons·lint-freshness 에 각각
복붙돼 있었고, lint-backlinks·lint-raw-coverage 에는 아예 없어 코드 예시 안의 `[[...]]`·
파일명이 진짜 링크·진짜 커버리지로 집계될 수 있었다 (2026-08-25 발견, 당시 실제 사례 0건인
잠복 상태). 사본은 드리프트한다 — 2026-08-18 에도 lint-links 만 "일지는 고아 면제"를 알게
되어 lint-index-stats 와 숫자가 갈렸다.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any

CODE_BLOCK = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE = re.compile(r"`[^`\n]*`")


def strip_code(text: str) -> str:
    """코드 블록·인라인 코드를 지운다. 그 안의 `[[X]]` 는 문법 예시지 링크가 아니다."""
    return INLINE_CODE.sub("", CODE_BLOCK.sub("", text))


def strip_fences(text: str) -> str:
    """펜스 코드 블록만 지운다. **인라인 코드는 남긴다.**

    ⚠️ 인용 형식이 검사마다 다르다 (2026-08-25 실측으로 갈림):
      - 위키링크는 인라인 코드 안에 있으면 문법 예시다 → strip_code
      - 파일명·경로는 인라인 코드가 **정상 인용 형식**이다 → strip_fences
        (`raw/conversations/260805-….md` 처럼 백틱으로 감싸 소스 페이지에 적는다)
    둘을 구분하지 않고 strip_code 를 raw 커버리지에 쓰면, 제대로 인용된 원본 4건이
    "소화 안 됨" 으로 잡혔다 — 검사를 엄격하게 만들다 오탐을 만든 사례.
    """
    return CODE_BLOCK.sub("", text)


def wants_json(argv: list[str] | None = None) -> bool:
    return "--json" in (argv if argv is not None else sys.argv)


def emit(script: str, ok: bool, problems: Any, **extra: Any) -> int:
    """`--json` 출력. 종료 코드는 텍스트 모드와 같은 규약(문제 있으면 1)을 쓴다."""
    payload = {"script": script, "ok": ok, "problems": problems}
    payload.update(extra)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if ok else 1
