#!/usr/bin/env python3
"""소스 페이지가 선언한 '갱신'이 실제로 반영됐는지 대조한다.

`wiki/1-sources/*.md` 의 「이 볼트에 미친 영향」에 "갱신: [[X]]" 라고 적혀 있으면,
X 가 그 소스를 근거로 인용(역링크)하고 있는지 확인한다.

두 종류의 누락을 구분한다:
  - 대상 없음   : [[X]] 페이지가 아예 없다 (심각)
  - 역링크 없음 : X 는 있으나 그 소스를 인용하지 않는다 (추적성 결함)

ingest 에서 가장 새기 쉬운 지점이라 매 lint 마다 돌린다
(2026-08-15 1차 lint 에서 내용 미반영 2건, 2차에서 역링크 누락 4건 발견).

사용법:
    python3 scripts/lint-backlinks.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lintlib import emit, strip_code, wants_json  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
IMPACT = re.compile(r"## 이 볼트에 미친 영향\n(.*?)(?=\n## |\Z)", re.S)
WIKILINK = re.compile(r"\[\[([^\]|#]+)\]\]")


def main() -> int:
    pages = {p.stem: p for p in ROOT.glob("wiki/**/*.md")}

    missing_page: list[tuple[str, str]] = []
    missing_link: list[tuple[str, str, str]] = []
    checked = 0

    for src in sorted((ROOT / "wiki/1-sources").glob("*.md")):
        # 코드 예시 안의 "갱신: [[X]]" 는 선언이 아니라 문법 설명이다 (2026-08-25 추가)
        m = IMPACT.search(strip_code(src.read_text(encoding="utf-8")))
        if not m:
            continue
        for line in m.group(1).splitlines():
            if "갱신" not in line:
                continue
            for target in (t.strip() for t in WIKILINK.findall(line)):
                checked += 1
                page = pages.get(target)
                if page is None:
                    missing_page.append((target, src.stem))
                elif f"[[{src.stem}]]" not in strip_code(
                    page.read_text(encoding="utf-8")
                ):
                    # 역링크가 코드블록 안에만 있으면 인용이 아니다 — 같은 이유로 걸러낸다
                    missing_link.append((target, src.stem, line.strip()[:80]))

    if wants_json():
        return emit(
            "lint-backlinks",
            not (missing_page or missing_link),
            {
                "대상 없음": [{"대상": t, "소스": s} for t, s in missing_page],
                "역링크 없음": [
                    {"대상": t, "소스": s, "선언": ln} for t, s, ln in missing_link
                ],
            },
            stats={"대조한 선언": checked},
        )

    print(f"=== 선언된 '갱신' {checked}건 대조 ===\n")

    print("[대상 페이지 없음]")
    if missing_page:
        for tgt, src in missing_page:
            print(f"  [[{tgt}]]  ← 선언한 소스: {src}")
    else:
        print("  없음")

    print("\n[역링크 없음 — 내용은 있을 수 있으나 출처를 못 따라감]")
    if missing_link:
        for tgt, src, line in missing_link:
            print(f"  [[{tgt}]]  ← {src}")
            print(f"      {line}")
    else:
        print("  없음")

    return 1 if (missing_page or missing_link) else 0


if __name__ == "__main__":
    raise SystemExit(main())
