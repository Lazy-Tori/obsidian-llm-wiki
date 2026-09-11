#!/usr/bin/env python3
"""일지 자동 생성 — 당일 일지를 캘린더 미러의 일정과 함께 만든다.

수동 "오늘 일지 써줘" 없이도 일지가 매일 생기게 한다 (2026-08-24 사용자 결정).
launchd(com.user.wiki-daily-gen)가 매일 07:00 에 실행하고, 잠들어 있었으면
깨어날 때 실행된다. 몇 번을 돌려도 안전하게(멱등) 설계했다:

- 당일 파일이 없으면 만든다 (2026-08-25 결정: D+7 선생성 철회 — 미래 골격은
  쓰임이 없었고 이월 병합 시 자리표시자 잔재만 남겼다).
- 오늘 일지에는 두 가지를 병합한다 (이미 있는 줄은 절대 건드리지 않는다):
  ① 캘린더에 새로 생긴 일정 추가  ② 직전 일지의 미완료 할일 이월 (`(MM-DD~)` 표시)
- 일정 출처는 `캘린더/YYYY-MM.md` (CalDAV 플러그인이 5분 주기로 재생성하는 미러).
  파일·섹션이 없으면 조용히 건너뛴다 — 오류를 내거나 추측으로 채우지 않는다 (규약 §12).
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DAILY = ROOT / "wiki" / "daily"
CALENDAR = ROOT / "캘린더"
RESERVE = ROOT / "예약.md"  # 미래 날짜 할일 — 그 날짜에 해야할일로 주입 후 제거
DAYS_AHEAD = 0
# 일지에는 업무 시간대 일정만 — 19:00 이후 시작하는 일정(저녁 개인 일정)은 제외
# (2026-08-24 사용자 결정)
CUTOFF_HOUR = 19

EVENT_ROW = re.compile(r"^\|\s*(\d{2}:\d{2})\s*-\s*\d{2}:\d{2}\s*\|\s*(.+?)\s*\|")
UNCHECKED = re.compile(r"^- \[ \] .+")
CARRIED = re.compile(r"\(\d{2}-\d{2}~\)\s*$")


def calendar_events(day: date) -> list[str]:
    """캘린더 미러에서 그날 일정을 "- HH:MM 제목" 목록으로. 없으면 빈 목록."""
    month_file = CALENDAR / f"{day:%Y-%m}.md"
    if not month_file.exists():
        return []
    lines = month_file.read_text(encoding="utf-8").splitlines()
    events: list[str] = []
    in_section = False
    for line in lines:
        if line.startswith("## "):
            in_section = line.startswith(f"## {day:%Y-%m-%d}")
            continue
        if in_section and (m := EVENT_ROW.match(line)):
            if int(m.group(1)[:2]) >= CUTOFF_HOUR:
                continue
            item = f"- {m.group(1)} {m.group(2)}"
            if item not in events:  # 반복 일정 중복 방어
                events.append(item)
    return events


def new_daily(day: date, events: list[str], todos: list[str]) -> str:
    schedule = "\n".join(events) if events else "(일정 없음)"
    todo_block = "\n".join(todos) if todos else "- [ ] "
    return f"""---
type: daily
title: {day:%Y-%m-%d}
domain: [work]
created: {date.today():%Y-%m-%d}
updated: {date.today():%Y-%m-%d}
tags: []
---

# {day:%Y-%m-%d}

## 일정

{schedule}

## 해야할일

{todo_block}

## 작업

## 정해진 것

## 이슈
"""


def carryover_todos(today: date) -> list[str]:
    """직전 일지의 미완료 할일 — **그룹 레이블을 보존해** 이월한다 (2026-08-25).

    해야할일 섹션 안에서 체크박스가 아닌 일반 텍스트 줄은 그룹 레이블로 본다.
    미완료 항목이 있는 그룹만, 레이블과 함께 옮긴다. 이월 표시 (MM-DD~) 는
    없으면 그 일지 날짜로 붙인다."""
    past = sorted(p for p in DAILY.glob("????-??-??.md") if p.stem < today.isoformat())
    if not past:
        return []
    src = past[-1]
    text = src.read_text(encoding="utf-8")
    m = re.search(r"## 해야할일\n(.*?)(?=\n## |\Z)", text, re.DOTALL)
    if not m:
        return []
    groups: list[tuple[str, list[str]]] = [("", [])]
    for line in m.group(1).splitlines():
        s = line.strip()
        if not s:
            continue
        if UNCHECKED.match(s):
            if s == "- [ ]":
                continue
            if not CARRIED.search(s):
                s = f"{s} ({src.stem[5:]}~)"
            groups[-1][1].append(s)
        elif not s.startswith("- ["):
            groups.append((s, []))          # 그룹 레이블
    out: list[str] = []
    for label, items in groups:
        if not items:
            continue
        if out:
            out.append("")
        if label:
            out.append(label)
        out.extend(items)
    return out


def merge_into_today(path: Path, events: list[str], todos: list[str]) -> bool:
    """오늘 일지에 캘린더 신규 일정·이월 할일을 추가한다. 있는 줄은 안 건드린다."""
    text = path.read_text(encoding="utf-8")
    changed = False

    def append_missing(section: str, items: list[str], txt: str) -> str:
        nonlocal changed
        m = re.search(rf"(## {section}\n)(.*?)(?=\n## |\Z)", txt, re.DOTALL)
        if not m:
            return txt
        body = m.group(2)

        # 이월 항목은 표시 유무와 무관하게 본문 대조 (같은 할일을 두 번 얹지 않게)
        def core(s: str) -> str:
            return CARRIED.sub("", s).strip()

        existing = {core(ln) for ln in body.splitlines()}
        missing = [i for i in items if core(i) not in existing]
        if not missing:
            return txt
        changed = True
        new_body = body.rstrip("\n").replace("(일정 없음)", "").rstrip("\n")
        new_body = (
            (new_body + "\n" if new_body.strip() else "") + "\n".join(missing) + "\n"
        )
        return txt[: m.start(2)] + new_body + txt[m.end(2) :]

    text = append_missing("일정", events, text)
    text = append_missing("해야할일", todos, text)
    if changed:
        path.write_text(text, encoding="utf-8")
    return changed


def reserved_todos(today) -> list[str]:
    """예약.md 에서 오늘(및 놓친 과거) 날짜 항목을 꺼내고 파일에서 제거한다."""
    import re as _re
    if not RESERVE.exists():
        return []
    lines = RESERVE.read_text(encoding="utf-8").splitlines()
    keep, due = [], []
    pat = _re.compile(r"^- (\d{4}-\d{2}-\d{2}) (.+)$")
    for line in lines:
        m = pat.match(line.strip())
        if m and m.group(1) <= today.isoformat():
            marker = (
                ""
                if m.group(1) == today.isoformat()
                else f" ({m.group(1)[5:]}~)"
            )
            due.append(f"- [ ] {m.group(2)}{marker}")
        else:
            keep.append(line)
    if due:
        RESERVE.write_text("\n".join(keep).rstrip("\n") + "\n", encoding="utf-8")
    return due


def is_empty_daily(text: str) -> bool:
    """사용자 내용이 전혀 없는 골격인가 — 일정조차 없으면 빈 일지다."""
    for sec in ("일정", "해야할일", "작업", "정해진 것", "이슈"):
        # 기계 줄은 애초에 일지에 없다 — 무인 실행이 남기는 사람 몫은
        # `볼트-백로그.md` 로
        # 간다 (2026-09-10 「볼트」 칸 폐지, 규약 §11)
        m = re.search(rf"## {sec}\n(.*?)(?=\n## |\Z)", text, re.DOTALL)
        if not m:
            continue
        body = m.group(1).replace("(일정 없음)", "").strip()
        lines = [
            ln.strip()
            for ln in body.splitlines()
            if ln.strip() and ln.strip() != "- [ ]"
        ]
        if lines:
            return False
    return True


def prune_empty_past(today) -> list[str]:
    """지난 날짜의 빈 일지를 삭제한다 (2026-08-25 사용자 결정).

    일정·해야할일·작업·정해진 것·이슈가 전부 비어 있으면 그날은 기록이 없는
    날이다 — 빈 파일은 거짓 기록이므로 지운다. git 추적이라 복구 가능."""
    removed = []
    for p in sorted(DAILY.glob("????-??-??.md")):
        if p.stem >= today.isoformat():
            continue
        if is_empty_daily(p.read_text(encoding="utf-8")):
            p.unlink()
            removed.append(p.stem)
    return removed


def main() -> None:
    DAILY.mkdir(parents=True, exist_ok=True)
    today = date.today()
    made, merged = [], []
    for offset in range(DAYS_AHEAD + 1):
        day = today + timedelta(days=offset)
        path = DAILY / f"{day:%Y-%m-%d}.md"
        events = calendar_events(day)
        todos = (carryover_todos(today) + reserved_todos(today)) if day == today else []
        if not path.exists():
            path.write_text(new_daily(day, events, todos), encoding="utf-8")
            made.append(path.stem)
        elif day == today and merge_into_today(path, events, todos):
            merged.append(path.stem)
    pruned = prune_empty_past(today)
    print(f"생성 {len(made)}개: {', '.join(made) if made else '—'}")
    if pruned:
        print(f"빈 일지 삭제 {len(pruned)}개: {', '.join(pruned)}")
    if merged:
        print(f"병합 {len(merged)}개: {', '.join(merged)}")


if __name__ == "__main__":
    main()
