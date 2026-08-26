#!/usr/bin/env python3
"""사실의 신선도 검사 — 스탬프 없이 "지금 그렇다"고 주장하는 줄을 찾는다.

배움과 개념은 시간이 지나도 안 썩지만 **휘발성 사실**(가격·한도·버전·인원·
대기 상태)은 썩는다. 문제는 썩은 줄이 여전히 참처럼 읽힌다는 것이다 —
`쿼터는 8장이다` 는 다음 달에 조용히 거짓말이 되지만 문장은 그대로다.
`lesson` 이 뒤집히면 그 페이지에 반례가 적힌다.

규약: `docs/wiki-conventions.md` §11. 모든 사실은 셋 중 하나여야 한다 —
  1. 무시간(timeless) — 안 썩으므로 날짜가 필요 없다
  2. 스냅샷(snapshot) — 날짜가 박힌 관측. 날짜 헤딩 아래는 자동으로 스냅샷
  3. 포인터(pointer) — 진실이 사는 곳을 가리킨다. 값은 선택

검사 항목:
  - FRESH-1: 휘발성 주장에 날짜가 없음 (스탬프를 붙이거나 포인터로 바꾼다)
  - FRESH-2: 날짜는 있는데 신선도 창(기본 90일)보다 오래됨 (재관측/변환/은퇴)
  - FRESH-3: 포인터인데 가리키는 대상(URL·경로·링크)이 없음

판정은 **한 줄 안에서** 끝난다 — 그 줄에 `YYYY-MM` 또는 `YYYY-MM-DD` 가 있으면
스탬프로 친다. 사람이 결과를 눈으로 검산할 수 있게 하려는 선택이다.

휴리스틱은 **정밀도 우선**이다. 휘발성 명사가 숫자와 12자 이내로 붙어 있을
때만 잡고, 과거형 문장(그 자체로 스냅샷)과 인용문(시점이 원문에 속한다)은
건너뛴다. 그래도 오탐은 남는다 — 오탐이면 날짜를 붙여 스냅샷으로 만들거나
표현을 고친다. 둘 다 위키가 좋아지는 방향이라 억지 회피가 아니다.

사용법:
    python3 scripts/lint-freshness.py [--window 90]
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lintlib import emit, wants_json  # noqa: E402

# 이 스크립트는 strip_code() 대신 줄 단위 FENCE 추적을 쓴다 — 문제 보고에 줄 번호가
# 필요해서 코드 블록을 지우면 번호가 밀린다
ROOT = Path(__file__).resolve().parent.parent
FM = re.compile(r"---\n(.*?)\n---", re.DOTALL)
FENCE = re.compile(r"^\s*```")
HEADING = re.compile(r"^#{1,6}\s+(.*)$")

# 스탬프 = 연-월 또는 연-월-일. 원본 정책의 `(as of YYYY-MM)` 허용과 같다
STAMP = re.compile(r"\d{4}-\d{2}(?:-\d{2})?")
# 인용된 발화는 시점이 원문에 속하므로 우리 주장이 아니다
QUOTE = re.compile(r"[\"“][^\"”]*[\"”]")

# 휘발성 명사. 추상적으로 남용되는 말(비용·순위·상한)은 일부러 뺐다 —
# 넣었더니 오탐이 72건이 되어 검사 자체가 무시당할 수준이었다
NOUN = r"(?:가격|요금|단가|한도|쿼터|정원|잔여|재고|환율|연봉|버전|인원|점유율|대기 중|미처리)"
# 숫자가 명사와 12자 이내로 붙어 있을 때만 휘발성 주장으로 본다
VOLATILE = re.compile(rf"{NOUN}[^.]{{0,12}}?\d|\d[^.]{{0,12}}?{NOUN}")
# 과거형은 그 자체로 스냅샷이다 — "588건을 검수했다" 는 안 썩는다
PAST = re.compile(
    r"(았|었|였|했|됐|왔|뒀|썼|봤|났|줬|겼|렸|쳤)(다|고|지만|는데|음|던|으며|며|다는|다가|기)"
)

POINTER = re.compile(r"진실이 사는 곳")
POINTER_TARGET = re.compile(r"https?://|`[^`]+`|\[\[|/")


def scan(path: Path, cutoff: str) -> list[tuple[str, str]]:
    """(코드, 메시지) 목록."""
    body = FM.sub("", path.read_text(encoding="utf-8"), count=1)
    found: list[tuple[str, str]] = []
    in_fence = False
    section_dated = False

    for lineno, raw in enumerate(body.splitlines(), start=1):
        if FENCE.match(raw):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        head = HEADING.match(raw)
        if head:
            # 날짜가 박힌 헤딩 아래는 전부 스냅샷이다 (FRESH-4 면제)
            section_dated = bool(STAMP.search(head.group(1)))
            continue

        line = raw.strip()
        if not line or line.startswith((">", "<!--", "---")):
            continue

        if POINTER.search(line) and not POINTER_TARGET.search(line):
            found.append(
                (
                    "FRESH-3",
                    f"{path.name}:{lineno} 포인터에 가리키는 대상이 없다 — {line[:60]}",
                )
            )
            continue

        if section_dated:
            continue

        claim = QUOTE.sub("", line)
        if not VOLATILE.search(claim) or PAST.search(claim):
            continue

        stamps = STAMP.findall(line)
        if not stamps:
            found.append(
                ("FRESH-1", f"{path.name}:{lineno} 날짜 없는 휘발성 주장 — {line[:70]}")
            )
        elif max(stamps) < cutoff:
            found.append(
                (
                    "FRESH-2",
                    f"{path.name}:{lineno} 스탬프 {max(stamps)} 가 창보다 오래됨 — {line[:60]}",
                )
            )

    return found


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", type=int, default=90, help="신선도 창(일). 기본 90")
    ap.add_argument("--json", action="store_true", help="기계 판독용 JSON 출력")
    args = ap.parse_args()
    cutoff = (date.today() - timedelta(days=args.window)).isoformat()

    all_pages = sorted(ROOT.glob("wiki/**/*.md"))
    pages = [
        p
        for p in all_pages
        if not p.read_text(encoding="utf-8").startswith("> 회사 위키 문서 원본")
    ]
    problems: list[tuple[str, str]] = []
    for path in pages:
        problems.extend(scan(path, cutoff))

    if wants_json():
        by_code: dict[str, list[str]] = {}
        for code, msg in problems:
            by_code.setdefault(code, []).append(msg)
        return emit(
            "lint-freshness",
            not problems,
            by_code,
            stats={"검사한 페이지": len(pages), "창": args.window},
        )

    print(f"=== 사실 신선도 검사 (wiki/ {len(pages)}개, 창 {args.window}일) ===\n")
    if not problems:
        print("  이상 없음")
        return 0

    for code, label in (
        ("FRESH-1", "날짜 없는 휘발성 주장"),
        ("FRESH-2", "스탬프가 창보다 오래됨"),
        ("FRESH-3", "대상 없는 포인터"),
    ):
        hits = [m for c, m in problems if c == code]
        if not hits:
            continue
        print(f"  [{code}] {label} {len(hits)}건")
        for m in hits:
            print(f"    ⚠️  {m}")
        print()
    print(
        "  → 재관측(스탬프 갱신) / 포인터로 변환 / 날짜 헤딩 아래로 은퇴 중 하나를 고른다"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
