#!/usr/bin/env python3
"""`index.md` 「현황」 숫자와 실제 집계 대조.

「현황」 블록은 손으로 쓴다. 목록 자체는 lint-links.py 가 지켜주지만(고아·깨진 링크)
집계 숫자는 지금까지 아무도 안 봤고, 그래서 조용히 어긋났다:
2026-08-15 소스 24→23·working 17→16 교정, 2026-08-17 페이지 68→67 교정.
둘 다 사람이 우연히 발견한 것이다 — 페이지를 지우고 현황을 안 고치면 아무 신호가 없다.

검사 항목:
  - 페이지 총계와 타입별 집계 (소스·배움·개념·산출물·시도·질문)
  - 링크 개수 · 깨진 링크 · 고아 페이지 (lint-links.py 와 같은 셈법)
  - confidence 분포 (solid·working·tentative)
  - inbox 잔량 (2026-08-25 추가)

⚠️ inbox 는 이 검사에 **없었다**. 「검사하지 않는 것」 목록에도 없어서 후보로 고려조차
안 됐다. 그동안 SessionEnd 훅이 세션마다 파일을 떨구는데도 현황은 `inbox: 0개` 인 채
"숫자 일치" 로 통과했다 — 하루 만에 거짓이 됐고 아무 신호가 없었다. inbox 잔량은
이 볼트에서 "안 읽은 게 얼마나 쌓였나" 를 알려주는 유일한 신호라 그게 틀리면
소화 상태 전체가 안 보인다. 조용한 실패를 잡으려고 만든 검사에 같은 구멍이 있었던 셈.

검사하지 않는 것: 「역링크 누락」은 lint-backlinks.py, 「raw/ 미처리」는
lint-raw-coverage.py 가 따로 본다. 「마지막 lint」 날짜는 기계가 알 수 없다.
「일지」도 세지 않는다 — actual() 이 daily 를 집계에서 빼므로 이 검사에서 일지 수는
항상 0 이다. 그걸 대조 항목으로 내보내면 현황에 참값을 적은 사람이 틀렸다고 보고된다.

⚠️ **대조 못 한 항목이 있으면 "숫자 일치" 라고 말하지 않는다** (2026-08-25 추가).
전에는 8개 항목(링크·깨진 링크·고아·개념·일지·confidence 3종)이 「현황」에 없어
검사 자체가 안 되는데도 헤드라인은 "숫자 일치" 였다 — 절반만 보고 전부 봤다고 말한 셈이라,
이 스크립트가 잡으려던 조용한 실패를 스스로 저지르고 있었다. 이제 부분 대조는
부분 대조라고 말한다.

사용법:
    python3 scripts/lint-index-stats.py
"""

from __future__ import annotations

import collections
import importlib.util
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lintlib import emit, wants_json  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.md"

# 링크·고아 셈법은 **lint-links.py 의 구현을 그대로 쓴다.** 사본을 두면 드리프트한다 —
# 실제로 2026-08-18 일지 도입 때 lint-links 만 "일지는 날짜로 찾으니 고아 면제"를 알게
# 되어 두 스크립트의 고아 수가 갈렸다. 그래서 복사 대신 import 로 바꿨다.
_links = importlib.util.spec_from_file_location(
    "lint_links", Path(__file__).resolve().parent / "lint-links.py"
)
lint_links = importlib.util.module_from_spec(_links)
_links.loader.exec_module(lint_links)

FM = re.compile(r"---\n(.*?)\n---", re.DOTALL)

# 프론트매터의 type ↔ 현황 줄에 쓰는 한국어 이름
TYPE_LABEL = {
    "source": "소스",
    "lesson": "배움",
    "concept": "개념",
    "build": "산출물",
    "experiment": "시도",
    "question": "질문",
    "project": "프로젝트",
}
# daily 는 actual() 에서 집계 전에 걸러진다 — 대조 항목으로 두면 항상 0 이라
# 현황에 참값을 적을수록 틀렸다고 나온다. TYPE_LABEL 에 넣지 않는 이유가 이것이다.
CONFIDENCE_ORDER = ["solid", "working", "tentative"]


def field(text: str, name: str) -> str:
    m = FM.match(text)
    if not m:
        return ""
    f = re.search(rf"^{name}:[ \t]*(.*)$", m.group(1), re.M)
    return f.group(1).strip() if f else ""


def inbox_count() -> int:
    """`inbox/` 의 미처리 파일 수. 폴더 유지용 `.gitkeep` 과 숨김 파일은 뺀다.

    inbox 는 "판단 0 착지" 버퍼라 하위 폴더를 두지 않는다 — 최상위만 센다.
    """
    box = ROOT / "inbox"
    if not box.is_dir():
        return 0
    return len([p for p in box.iterdir() if p.is_file() and not p.name.startswith(".")])


def actual() -> dict[str, int]:
    types: collections.Counter[str] = collections.Counter()
    confidence: collections.Counter[str] = collections.Counter()
    for path in ROOT.glob("wiki/**/*.md"):
        text = path.read_text(encoding="utf-8")
        # 회사 위키 문서 원본(외부 시스템 미러, 프론트매터 없음)은 승격 사다리의
        # "페이지"가 아니라 프로젝트 페이지의 첨부물이라 집계에서 제외한다.
        if text.startswith("> 회사 위키 문서 원본"):
            continue
        # daily 는 집계에서 제외한다 (2026-08-24): 자동 생성기가 D+7 골격을 미리
        # 만들어 매일 +1 씩 늘어나므로, 세면 현황이 날마다 어긋난다. 시간 기록이라
        # 내용 카탈로그(index)의 신호도 아니다 — 현황에는 "일지 제외"로 명시한다.
        if field(text, "type") == "daily":
            continue
        types[field(text, "type")] += 1
        c = field(text, "confidence")
        if c:
            confidence[c] += 1

    pages, links, _ = lint_links.collect()
    orphans = [
        n
        for n in pages
        if n not in links
        and n not in lint_links.NOT_A_PAGE
        and not lint_links.DATED_PAGE.match(n)
    ]

    stats = {
        "페이지": sum(types.values()),
        "링크": sum(len(v) for v in links.values()),
        "깨진 링크": len([t for t in links if t not in pages]),
        "고아": len(orphans),
        "inbox": inbox_count(),
    }
    for t, label in TYPE_LABEL.items():
        stats[label] = types[t]
    for c in CONFIDENCE_ORDER:
        stats[c] = confidence[c]
    return stats


def declared(text: str) -> dict[str, int]:
    """「현황」 블록에 사람이 적어둔 숫자를 뽑는다."""
    m = re.search(r"^## 현황$(.*?)(?=^---|\Z)", text, re.M | re.DOTALL)
    if not m:
        return {}
    block = m.group(1)

    out: dict[str, int] = {}
    patterns = {
        "페이지": r"\*\*(\d+)\s*페이지\*\*",
        "링크": r"링크\s+(\d+)개",
        "깨진 링크": r"깨진 링크\s+(\d+)",
        "고아": r"고아\s+(\d+)",
        # `- inbox: 0개 — …` 형식. 「현황」에 이 줄이 없으면 대조 대상에서 빠진다
        "inbox": r"inbox:\s*(\d+)\s*개",
    }
    patterns |= {label: rf"{label}\s+(\d+)" for label in TYPE_LABEL.values()}
    patterns |= {c: rf"{c}\s+(\d+)" for c in CONFIDENCE_ORDER}

    for key, pattern in patterns.items():
        found = re.search(pattern, block)
        if found:
            out[key] = int(found.group(1))
    return out


def main() -> int:
    if not INDEX.exists():
        print("index.md 없음")
        return 1

    text = INDEX.read_text(encoding="utf-8")
    want, have = declared(text), actual()

    if not want:
        print("=== index.md 현황 대조 ===\n")
        print("  ⚠️  「## 현황」 블록을 찾지 못했다")
        return 1

    problems = [
        f"{key}: 현황에 {want[key]} 이라고 적혀 있으나 실제는 {have[key]}"
        for key in want
        if key in have and want[key] != have[key]
    ]
    missing = [k for k in have if k not in want]

    checked = len(want)
    total = len(have)

    # 총계와 세부합이 서로 안 맞는 자기모순 — 실제와 별개로 잡는다.
    # 출력보다 먼저 판정해야 --json 과 텍스트가 같은 결론을 낸다
    parts = [want[label] for label in TYPE_LABEL.values() if label in want]
    self_contra = (
        "페이지" in want
        and len(parts) == len(TYPE_LABEL)
        and sum(parts) != want["페이지"]
    )
    if self_contra:
        problems.append(
            f"현황 안에서 자기모순: 세부합 {sum(parts)} ≠ 총계 {want['페이지']}"
        )

    if wants_json():
        # 대조 못 한 항목(missing)은 실패가 아니다 — 텍스트 모드의 「부분 대조」와 같은 판정.
        # 커버리지 부족은 보고하되 exit 1 로 올리지 않는다
        return emit(
            "lint-index-stats",
            not problems,
            {"숫자 불일치": problems, "대조 못 함": missing},
            stats={"대조": checked, "전체": total},
            선언=want,
            실제=have,
        )

    print(f"=== index.md 현황 대조 ({checked}/{total}개 항목) ===\n")
    if problems:
        for p in problems:
            print("  ⚠️  ", p)
    elif missing:
        # 통과가 아니라 "본 것까지는 맞다" 다. 헤드라인이 커버리지를 말해야
        # 안 본 항목이 통과로 읽히지 않는다
        print(f"  부분 대조 — 본 {checked}개는 일치, {len(missing)}개는 검사 못 함")
    else:
        print("  숫자 일치 (전 항목)")
    if missing:
        print(f"\n  (현황에 적혀 있지 않아 대조 못 한 항목: {', '.join(missing)})")
        print("   → index.md 「현황」에 그 줄을 추가하면 이 검사가 지켜준다")

    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
