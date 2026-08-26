#!/usr/bin/env python3
"""프론트매터 필드 검사.

lint 판정이 프론트매터에 의존하므로, 필드가 빠지면 판정이 통째로 누락된다.
실제로 2026-08-15 속성을 훑어보고 나서야 소스 23개의 `updated` 누락이 드러났다 —
빠진 필드는 오류를 내지 않고 조용히 검사 밖으로 빠진다.

검사 항목:
  - 공통 필수 필드 (source 는 created 대신 ingested)
  - 날짜 형식 YYYY-MM-DD
  - updated < created (시간 역전)
  - 타입별 필드 값이 허용 집합 안에 있는지

사용법:
    python3 scripts/lint-frontmatter.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lintlib import emit, wants_json  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FM = re.compile(r"---\n(.*?)\n---", re.DOTALL)
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

COMMON = ["type", "title", "domain", "updated"]
# source 는 created 대신 ingested 를 쓴다 (docs/wiki-conventions.md §1)
CREATED_FIELD = {"source": "ingested"}

ALLOWED = {
    "experiment": {"status": {"running", "done", "abandoned", "paused"}},
    "project": {"status": {"active", "paused", "done"}},
    "daily": {},
    "lesson": {"confidence": {"tentative", "working", "solid"}},
    "build": {"status": {"idea", "wip", "shipped", "archived"}},
    "concept": {"maturity": {"stub", "growing", "stable"}},
    "question": {"status": {"open", "answered", "dropped"}},
    # 여기 status 는 폐기 경로(답이 틀렸다고 판명)만 담당한다.
}


def parse(path: Path) -> dict[str, str] | None:
    m = FM.match(path.read_text(encoding="utf-8"))
    if not m:
        return None
    # `\s*` 를 쓰면 `\s` 가 개행을 포함해 **빈 필드가 다음 줄을 삼킨다** —
    # 빈 필드는 채워진 것으로 보이고 바로 다음 필드는 사라져, 필수 필드·허용값 검사가
    # 동시에 조용히 무력화된다 (2026-08-17 발견).
    return dict(re.findall(r"^(\w+):[ \t]*(.*)$", m.group(1), re.M))


def main() -> int:
    problems: list[str] = []
    checked = 0

    for path in sorted(ROOT.glob("wiki/**/*.md")):
        text = path.read_text(encoding="utf-8")
        name = path.stem
        # 회사 위키 문서 원본(외부 시스템 미러) — 첫 줄이 이 마커면 프론트매터 없이도
        # 원문 그대로 wiki/projects/<프로젝트>/ 에 둘 수 있다 (docs/wiki-conventions.md §2)
        if text.startswith("> 회사 위키 문서 원본"):
            continue
        d = parse(path)
        if d is None:
            problems.append(f"{name}: 프론트매터 없음")
            continue
        checked += 1

        ptype = d.get("type", "")
        required = COMMON + [CREATED_FIELD.get(ptype, "created")]
        for field in required:
            if field not in d:
                problems.append(f"{name}: 필수 필드 `{field}` 없음")
            elif not d[field].strip():
                # 필드명만 있고 값이 빈 경우. 위 파서 버그가 이걸 통째로 가리고 있었다 —
                # 빈 값은 필드가 있는 것으로 보여 검사를 조용히 통과한다
                problems.append(f"{name}: 필수 필드 `{field}` 가 비었음")

        for field in ("created", "updated", "ingested"):
            v = d.get(field, "").strip()
            if v and not DATE.fullmatch(v):
                problems.append(f"{name}: `{field}` 가 YYYY-MM-DD 아님 ({v!r})")

        start = d.get(CREATED_FIELD.get(ptype, "created"), "").strip()
        end = d.get("updated", "").strip()
        if DATE.fullmatch(start) and DATE.fullmatch(end) and end < start:
            problems.append(f"{name}: updated({end}) 가 시작일({start}) 보다 과거")

        for field, allowed in ALLOWED.get(ptype, {}).items():
            v = d.get(field, "").strip()
            if v and v not in allowed:
                problems.append(
                    f"{name}: `{field}={v}` 는 허용값이 아님 {sorted(allowed)}"
                )

    if wants_json():
        return emit(
            "lint-frontmatter",
            not problems,
            {"프론트매터": problems},
            stats={"검사한 페이지": checked},
        )

    print(f"=== 프론트매터 검사 ({checked}개) ===\n")
    if problems:
        for p in problems:
            print("  ⚠️ ", p)
    else:
        print("  이상 없음")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
