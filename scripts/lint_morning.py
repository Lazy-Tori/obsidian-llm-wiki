#!/usr/bin/env python3
"""매일 08:30 launchd 가 부르는 무인 lint (규약 §8.1).

흐름:
  1. `lint_autofix.py` — 정답이 하나뿐인 것만 고친다 (LLM 없음, 결정론적)
  2. `lint_all.py --json` — 남은 발견을 수집
  3. 남은 것을 **그날 일지 「이슈」**에 체크박스로 적는다 (위키 다른 곳은 안 건드림)
  4. 고친 게 있으면 `log.md` 기록 + `auto-lint |` 커밋

⚠️ **수정 권한은 여기서 끝난다.** 이슈에 적힌 것은 사람이 "고쳐줘" 라고 해야 손댄다 —
문장을 쓰거나 의도를 추측해야 하는 것들이라, 무인이 건드리면 되돌릴 근거가 안 남는다.

⚠️ 일지 「이슈」는 **이월되지 않는다** (carryover 는 「해야할일」만 읽는다). 대신 매일
아침 재검사에서 문제가 남아 있으면 같은 줄을 다시 적으므로, 고칠 때까지 계속 나타나고
고치면 저절로 사라진다 — 이월보다 정확하다. 같은 줄이 이미 있으면 중복 추가하지 않는다.

사용법:
    python3 scripts/lint_morning.py
    python3 scripts/lint_morning.py --dry-run   # 일지·log·커밋 없이 무엇을 할지만
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
DAILY = ROOT / "wiki" / "daily"
LOG = ROOT / "log.md"
MARK = "- [ ] lint("  # 일지에 적는 줄의 표식 — 자기 참조 판정에 쓴다

# 이슈에 적을 때 쓰는 사람이 읽는 이름
LABEL = {
    "lint-links": "링크",
    "lint-backlinks": "역링크",
    "lint-frontmatter": "프론트매터",
    "lint-index-stats": "현황 숫자",
    "lint-freshness": "사실 신선도",
    "lint-lessons": "lesson 하향",
    "lint-raw-coverage": "raw 소화",
}


def run(args: list[str]) -> tuple[int, str]:
    p = subprocess.run(
        [sys.executable, *args], cwd=ROOT, capture_output=True, text=True
    )
    return p.returncode, p.stdout + p.stderr


def findings() -> list[str]:
    """남은 발견을 사람이 읽는 한 줄들로. 항목이 많으면 개수로 줄인다."""
    _, out = run([str(SCRIPTS / "lint_all.py"), "--json"])
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return ["lint 결과를 읽지 못했다 — 스크립트가 깨졌을 수 있다"]

    lines = []
    for check in data.get("검사", []):
        if check.get("ok"):
            continue
        name = LABEL.get(check.get("script", ""), check.get("script", "?"))
        for kind, items in (check.get("problems") or {}).items():
            n = len(items) if isinstance(items, (list, dict)) else 0
            if not n:
                continue
            first = ""
            if isinstance(items, list) and isinstance(items[0], str):
                first = f" — {items[0][:70]}"
            elif isinstance(items, dict):
                first = f" — {list(items)[0][:70]}"
            lines.append(f"{name}/{kind} {n}건{first}")
    return lines


def write_issues(lines: list[str], dry: bool) -> list[str]:
    """그날 일지 「볼트」에 체크박스로 적는다 (「이슈」는 사람의 업무 이슈 전용). 일지가 없으면 만들지 않는다 —
    일지 생성은 generate-daily.py 의 일이고, 07:00 에 이미 돌았어야 한다."""
    path = DAILY / f"{date.today():%Y-%m-%d}.md"
    if not path.exists():
        return [f"(일지 {path.stem} 없음 — 이슈를 적지 못했다)"]

    text = path.read_text(encoding="utf-8")
    m = re.search(r"^## 볼트\s*$(.*?)(?=^## |\Z)", text, re.M | re.DOTALL)
    if not m:
        return ["(일지에 「볼트」 섹션이 없다)"]

    body = m.group(1)
    added = []
    for line in lines:
        # ⚠️ 줄에 날짜를 박는 이유 (2026-08-25 실측):
        # 스탬프가 없으면 다음날 lint-freshness 가 이 줄을 「날짜 없는 휘발성 주장」으로
        # 잡고, 그 발견이 다시 이슈로 적혀 **매일 줄이 불어나는 자기 참조 루프**가 된다.
        # 날짜는 그 검사를 만족시키면서 "언제 처음 걸렸나" 도 알려준다
        entry = f"- [ ] lint({date.today():%Y-%m-%d}): {line}"
        # 같은 발견이 이미 있으면 다시 적지 않는다 (매일 재검사라 중복이 쌓인다)
        if line.split(" — ")[0] in body:
            continue
        # 이 줄 자체를 지목한 발견도 무시한다 (일지 lint 줄을 근거로 삼는 발견)
        if f"{DAILY.name}/{date.today():%Y-%m-%d}.md" in line or MARK in line:
            continue
        body = body.rstrip("\n") + "\n" + entry + "\n"
        added.append(entry)

    if added and not dry:
        path.write_text(text[: m.start(1)] + body + text[m.end(1) :], encoding="utf-8")
    return added


def append_log(fixed: str, issues: list[str], dry: bool) -> None:
    if dry:
        return
    entry = [f"\n## [{date.today():%Y-%m-%d}] lint | 무인 실행\n"]
    entry.append(f"- 자동 수정: {fixed.strip() or '없음'}")
    if issues:
        entry.append(f"- 일지 「이슈」로 넘김 {len(issues)}건:")
        entry += [f"  - {i.replace('- [ ] ', '')}" for i in issues]
    entry.append("- 이슈 항목은 사람이 「고쳐줘」 라고 해야 손댄다 (규약 §8.1)")
    LOG.write_text(
        LOG.read_text(encoding="utf-8") + "\n".join(entry) + "\n", encoding="utf-8"
    )


def dirty() -> set[str]:
    out = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True
    ).stdout
    return {ln[3:].strip().strip('"') for ln in out.splitlines() if ln.strip()}


def commit(paths: set[str], dry: bool) -> None:
    """**자기가 건드린 파일만** 커밋한다.

    `git add -A` 를 쓰면 작업 중이던 무관한 변경까지 `auto-lint |` 로 쓸어담아
    이력에서 "무인 실행이 뭘 고쳤나" 를 못 읽는다 (2026-08-25 실측으로 발견).
    나머지는 obsidian-git 의 10분 자동 백업이 알아서 가져간다."""
    if dry or not paths:
        return
    subprocess.run(["git", "add", "--", *sorted(paths)], cwd=ROOT, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", f"auto-lint | {date.today():%Y-%m-%d} 무인 점검"],
        cwd=ROOT,
        capture_output=True,
    )


def main() -> int:
    dry = "--dry-run" in sys.argv
    before = dirty()  # 이 실행 이전부터 있던 변경 — 커밋에서 제외한다

    fix_args = [str(SCRIPTS / "lint_autofix.py")] + (["--dry-run"] if dry else [])
    _, fixed_out = run(fix_args)
    print(fixed_out)

    # 자동 수정기가 "거부" 한 항목(inbox 미처리 등)은 lint 원문보다 행동이 분명하다.
    # 그쪽 문장을 그대로 이슈에 싣는다
    deferred = [
        ln.replace("⚠️", "").strip() for ln in fixed_out.splitlines() if "⚠️" in ln
    ]
    remaining = deferred + findings()
    issues = write_issues(remaining, dry) if remaining else []

    print("=== 일지 「이슈」 ===\n")
    if issues:
        for i in issues:
            print(f"  {i}")
    elif remaining:
        print("  (이미 적혀 있음 — 중복 추가 안 함)")
    else:
        print("  남은 발견 없음")

    mine = dirty() - before  # 이 실행이 만든 변경만
    if mine and not dry:
        append_log(fixed_out, issues, dry)
        mine |= {"log.md"}
        commit(mine, dry)
        print(f"\n커밋: {', '.join(sorted(mine))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
