#!/usr/bin/env python3
"""lesson 하향 경로 검사 — 승격 사다리에는 내려가는 길도 있어야 한다.

근거 → `lesson` 이 올라가는 축이고, `wiki-emerge` 가 그걸 찾는다. 그런데 **한 번 올라간 배움이 조용히 죽는 경로**는 아무도 안 봤다.
배움이 죽는 방식은 셋이다:

  - **반박됨** — 새 경험이 뒤집는다 → `confidence` 를 낮추고 반례에 적는다(사람의 일)
  - **대체됨** — 더 나은 배움이 자리를 가져간다 → `superseded_by` 로 **선언**한다
  - **방치됨** — 아무도 다시 안 쓴다 → 이건 **계산**한다 (아래)

방치를 자기 `updated` 만으로 보면 부정확하다. 배움은 다시 쓰일 때 강해지는데,
인용은 인용하는 쪽 페이지에서 일어나기 때문이다. 그래서 **마지막 강화 시점 =
max(자기 updated, 이 페이지를 링크한 페이지들의 updated)** 로 계산한다.

낡음을 `status` 로 선언하지 않는 이유 —
선언과 계산을 이중으로 두면 드리프트가 생긴다. 계산할 수 없는 것(대체)만 선언한다.

검사 항목:
  - 방치: 마지막 강화가 창(기본 180일)보다 오래된 lesson
  - 대체 링크 깨짐: `superseded_by` 가 없는 페이지를 가리킴
  - 대체된 것을 인용 중: `superseded_by` 가 붙은 lesson 을 아직 링크하는 페이지
  - confidence 계약: `solid` 인데 근거가 2개 미만이거나 반례 항목이 비었음
  - 승급 후보: `tentative` 인데 근거가 2개 이상 (정보성)

사용법:
    python3 scripts/lint-lessons.py [--window 180]
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lintlib import emit, strip_code, wants_json  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FM = re.compile(r"---\n(.*?)\n---", re.DOTALL)
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
WIKILINK = re.compile(r"\[\[([^\]|#]+)")
# 「## 근거」 부터 다음 `##` 직전까지
EVIDENCE = re.compile(r"^## 근거\s*$(.*?)(?=^## |\Z)", re.M | re.DOTALL)
COUNTER = re.compile(r"^## 반례[^\n]*$(.*?)(?=^## |\Z)", re.M | re.DOTALL)


def parse_fm(path: Path) -> dict[str, str]:
    m = FM.match(path.read_text(encoding="utf-8"))
    if not m:
        return {}
    # `\s*` 를 쓰면 빈 필드가 다음 줄 값을 삼킨다 (2026-08-17 발견)
    return dict(re.findall(r"^(\w+):[ \t]*(.*)$", m.group(1), re.M))


def body_of(path: Path) -> str:
    return strip_code(FM.sub("", path.read_text(encoding="utf-8"), count=1))


def links_in(text: str) -> list[str]:
    seen: list[str] = []
    for target in WIKILINK.findall(text):
        name = target.strip()
        if name and name not in seen:
            seen.append(name)
    return seen


def section(pattern: re.Pattern, text: str) -> str:
    m = pattern.search(text)
    return m.group(1) if m else ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--window", type=int, default=180, help="방치 판정 창(일). 기본 180"
    )
    ap.add_argument("--json", action="store_true", help="기계 판독용 JSON 출력")
    args = ap.parse_args()
    cutoff = (date.today() - timedelta(days=args.window)).isoformat()

    all_pages = sorted(ROOT.glob("wiki/**/*.md"))
    stems = {p.stem for p in all_pages}
    updated_of = {p.stem: parse_fm(p).get("updated", "").strip() for p in all_pages}

    # 누가 누구를 링크하는가 — 강화 시점 계산과 "대체된 것 인용 중" 검사에 쓴다
    inbound: dict[str, list[str]] = {}
    for path in all_pages:
        for target in links_in(body_of(path)):
            inbound.setdefault(target, []).append(path.stem)

    lessons = sorted(ROOT.glob("wiki/2-lessons/*.md"))
    problems: list[str] = []
    notes: list[str] = []

    for path in lessons:
        fm = parse_fm(path)
        name = path.stem
        text = body_of(path)
        conf = fm.get("confidence", "").strip()
        superseded = fm.get("superseded_by", "").strip()

        evidence = links_in(section(EVIDENCE, text) or text)
        evidence = [t for t in evidence if t in stems and t != name]

        if conf == "solid":
            if len(evidence) < 2:
                problems.append(
                    f"{name}: confidence solid 인데 근거 링크가 {len(evidence)}개 — 2개 이상이어야 한다"
                )
            if not section(COUNTER, text).strip():
                problems.append(
                    f"{name}: confidence solid 인데 「반례 / 긴장」이 비었음 — "
                    f"solid 는 '반례를 찾아봤고 견뎠다'는 주장이다"
                )
        elif conf == "tentative" and len(evidence) >= 2:
            notes.append(
                f"{name}: tentative 인데 근거가 {len(evidence)}개 — working 승급 후보"
            )

        if superseded:
            target = (links_in(superseded) or [superseded])[0]
            if target not in stems:
                problems.append(
                    f"{name}: superseded_by 가 없는 페이지를 가리킴 — [[{target}]]"
                )
            citers = [s for s in inbound.get(name, []) if s != target]
            if citers:
                problems.append(
                    f"{name}: 대체됐는데 아직 인용 중 — {', '.join(f'[[{c}]]' for c in citers)} "
                    f"(→ [[{target}]] 로 옮길지 확인)"
                )
            continue

        # 방치 = 자기 갱신과 인용한 쪽 갱신 중 최신이 창보다 오래됨
        marks = [updated_of.get(name, "")] + [
            updated_of.get(s, "") for s in inbound.get(name, [])
        ]
        marks = [m for m in marks if DATE.fullmatch(m)]
        if not marks:
            continue
        last = max(marks)
        if last < cutoff:
            problems.append(
                f"{name}: 마지막 강화가 {last} — {args.window}일 넘게 아무도 다시 쓰지 않았다 "
                f"(유효/대체/보관 중 하나를 정한다)"
            )

    if wants_json():
        return emit(
            "lint-lessons",
            not problems,
            {"lesson 하향": problems},
            stats={"lesson": len(lessons), "방치 창": args.window},
            참고=notes,
        )

    print(
        f"=== lesson 하향 경로 검사 ({len(lessons)}개, 방치 창 {args.window}일) ===\n"
    )
    if not lessons:
        print("  lesson 페이지 없음")
        return 0
    for p in problems:
        print("  ⚠️ ", p)
    for n in notes:
        print("  ℹ️ ", n)
    if not problems and not notes:
        print("  이상 없음")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
