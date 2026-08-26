#!/usr/bin/env python3
"""raw 원본이 실제로 소화됐는가 — raw → wiki 커버리지 검사.

이 볼트의 파이프라인은 `inbox → raw → wiki` 다. 그런데 **raw 에 갖다 놓고 끝내도
아무 신호가 없었다.** index.md 의 「raw/ 미처리: 0개」는 손으로 쓴 주장이라
실제와 어긋나도 조용하다 — 2026-08-18 save 발췌를 raw/conversations/ 로 옮기면서
wiki 참조 없이 방치한 것을 사용자가 지적해 만든 검사다.
("소화를 시키면 raw → wiki 까지 진행되어야 한다")

커버 판정: 그 원본을 가리키는 wiki 페이지가 하나라도 있으면 소화된 것으로 본다.
  - 파일명(basename) 이 wiki 어딘가에 등장하거나
  - 앞자리 숫자 ID(회사 위키 export 의 페이지 번호)가 등장하거나
  - **대량 채널**(notes)은 채널 폴더 경로가 등장하면 전체를 커버로 본다 —
    이 채널들은 배치 단위로 소스 페이지를 만들기 때문이다
    (`source_file: raw/notes/ (2025-09 ~ 2025-11)` 형식)

검사 제외: `assets/`(첨부는 참조되는 쪽) · `personal/credentials/`(ingest 비대상)

사용법:
    python3 scripts/lint-raw-coverage.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lintlib import emit, strip_fences, wants_json  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"

# 배치 단위로 소화하는 채널 — 채널 경로가 인용되면 전체 커버로 본다
BULK = {"notes"}
# 검사 대상이 아닌 채널
SKIP = {"assets"}
SKIP_DIRS = {RAW / "personal" / "credentials"}

ID = re.compile(r"^(\d{6,})-")


def wiki_text() -> str:
    """커버 판정의 근거가 되는 wiki 전문. 펜스 코드 블록만 뺀다 (2026-08-25 추가) —
    코드 예시에 파일명이 등장했다고 소화된 건 아니다. 단 **인라인 코드는 남긴다** —
    이 볼트는 원본을 `260805-….md` 처럼 백틱으로 인용하므로 그게 정상 커버다."""
    return "\n".join(
        strip_fences(p.read_text(encoding="utf-8")) for p in ROOT.glob("wiki/**/*.md")
    )


def main() -> int:
    text = wiki_text()
    uncovered: list[str] = []
    checked = 0

    for path in sorted(RAW.rglob("*.md")):
        rel = path.relative_to(RAW)
        channel = rel.parts[0]
        if channel in SKIP or any(str(path).startswith(str(d)) for d in SKIP_DIRS):
            continue
        if channel in BULK:
            # 채널 자체가 인용됐는지만 본다 (배치 소화)
            if f"raw/{channel}/" not in text:
                uncovered.append(
                    f"raw/{channel}/ 채널 전체 — 이 채널을 가리키는 소스 페이지가 없다"
                )
                BULK.discard(channel)  # 한 번만 보고
            continue

        checked += 1
        keys = [path.name, path.stem]
        m = ID.match(path.name)
        if m:
            keys.append(m.group(1))
        if not any(k in text for k in keys):
            uncovered.append(f"{rel}")

    if wants_json():
        return emit(
            "lint-raw-coverage",
            not uncovered,
            {"소화 안 됨": uncovered},
            stats={"개별 검사": checked},
        )

    print(f"=== raw → wiki 커버리지 ({checked}개 개별 검사 + 배치 채널) ===\n")
    if not uncovered:
        print("  전부 소화됨")
        return 0

    print(
        f"  ⚠️  소화 안 된 원본 {len(uncovered)}건 — raw 에만 있고 wiki 가 안 가리킨다:"
    )
    for u in uncovered:
        print(f"      {u}")
    print("\n  → ingest 하거나(소스 페이지 + 영향 페이지 갱신),")
    print("     index.md 「현황」의 `raw/ 미처리` 숫자를 실제와 맞춘다")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
