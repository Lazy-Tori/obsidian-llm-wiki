#!/usr/bin/env python3
"""세션 시작 훅 — 오늘 일지 「볼트」의 미처리 줄을 컨텍스트로 주입한다.

무인 ingest(08:00)·무인 점검(08:30)이 자기 권한 밖이라 남긴 잔여 작업을,
사람이 Claude Code 를 여는 순간 눈앞에 올린다. 사람이 "체크하는 것"을 기억해야
도는 구조를 피하려는 것 — 이미 하는 행동(세션을 연다)에 얹는다.

**보고만 한다.** 실행은 사람이 승인한 뒤 대화형으로(wiki-ingest·wiki-lint).
무인이 기존 페이지를 고치지 않는다는 규약 §6.2·§8.1 을 우회하지 않기 위해서다.

조용함 규칙:
- 미처리 줄이 없으면 아무것도 출력하지 않는다 (무관한 프로젝트 세션에서의 소음 방지)
- 같은 잔량은 하루 1회만. 잔량이 바뀌면 그날 안이라도 다시 알린다
- **사람이 없는 세션에서는 침묵한다** (`VAULT_HOOK_SILENT` / `claude -p`)

⚠️ 마지막 규칙의 이유 (2026-08-26 실측): 이 알림은 사람에게 승인을 구하는 말인데,
`claude -p` 로 도는 자동화(세션 요약기·무인 ingest)에도 그대로 주입됐다. 요약기는
자기 컨텍스트에 들어온 이 잔여 작업을 **요약 대상 세션의 「다음 할 일」로 적었고**,
그 소스 페이지가 다시 위키로 들어왔다 — 기계가 쓴 줄을 기계가 다시 읽는 되먹임.
근본 수정은 주입 단계에서 끊는 것이다(요약 프롬프트를 손보는 게 아니라).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

# 이 스크립트는 볼트 안(scripts/)에 살므로 자기 위치로 볼트를 찾는다 —
# 훅은 임의의 디렉토리에서 불리기 때문에 cwd 에 기댈 수 없다.
# 심볼릭 링크 등으로 밖에 두고 쓸 때만 VAULT_PATH 로 덮어쓴다.
VAULT = Path(
    os.environ.get("VAULT_PATH") or Path(__file__).resolve().parent.parent
).expanduser()
STATE = Path.home() / ".claude" / ".vault-backlog-state.json"

SECTION = re.compile(r"^## 볼트\s*$(.*?)(?=^## |\Z)", re.M | re.DOTALL)
UNCHECKED = re.compile(r"^- \[ \] (.+)$", re.M)


def backlog_lines(today: str) -> list[str]:
    """오늘 일지 「볼트」 섹션의 미완료 항목. 일지가 없으면 빈 목록."""
    daily = VAULT / "wiki" / "daily" / f"{today}.md"
    if not daily.is_file():
        return []
    section = SECTION.search(daily.read_text(encoding="utf-8"))
    if not section:
        return []
    return [m.strip() for m in UNCHECKED.findall(section.group(1))]


def is_hook_run() -> bool:
    """훅으로 불렸는지(세션 시작 JSON 을 stdin 으로 받는다) 판별.

    수동 실행·테스트가 「하루 1회」 슬롯을 먹어 정작 세션에서 침묵하는 사고가 있었다
    (2026-08-26). 사람이 실제로 본 실행만 상태를 쓴다.
    """
    if sys.stdin.isatty():
        return False
    try:
        payload = json.loads(sys.stdin.read())
    except (OSError, ValueError):
        return False
    return isinstance(payload, dict) and "session_id" in payload


def already_shown(today: str, digest: str) -> bool:
    """같은 잔량을 오늘 이미 알렸는지. 상태 파일이 깨져 있으면 알린 적 없는 것으로 본다."""
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return state.get("date") == today and state.get("digest") == digest


def mark_shown(today: str, digest: str) -> None:
    try:
        STATE.write_text(
            json.dumps({"date": today, "digest": digest}, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        pass  # 알림 자체가 실패할 이유는 안 된다


def skill_for(line: str) -> str:
    """줄머리 접두사로 담당 스킬을 가른다 (ingest_morning.sh · lint_morning.py 가 박는다)."""
    # 날짜 괄호가 붙기 전 형식(`ingest:`)도 받는다 — 옛 줄이 일지에 남아 있다
    if line.startswith("lint"):
        return "wiki-lint"
    return "wiki-ingest"


def is_headless() -> bool:
    """사람이 보고 있지 않은 세션인가 — 그러면 알릴 상대가 없다.

    - `VAULT_HOOK_SILENT`: 볼트 자동화가 `claude -p` 를 띄울 때 직접 박는다 (확실한 신호)
    - `CLAUDE_CODE_ENTRYPOINT == sdk-cli`: `claude -p`(print 모드)의 값. 대화형은 `cli` 다.
      **모르는 값은 사람으로 취급한다** — 침묵이 기본값이 되면 알림이 조용히 죽는다
    """
    if os.environ.get("VAULT_HOOK_SILENT"):
        return True
    return os.environ.get("CLAUDE_CODE_ENTRYPOINT") == "sdk-cli"


def main() -> int:
    if is_headless():
        return 0
    today = f"{date.today():%Y-%m-%d}"
    lines = backlog_lines(today)
    if not lines:
        return 0

    hook_run = is_hook_run()
    digest = hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()[:12]
    if hook_run and already_shown(today, digest):
        return 0

    skills = sorted({skill_for(line) for line in lines})
    body = "\n".join(
        [f"[볼트] 오늘 일지({today}) 「볼트」에 미처리 {len(lines)}건:"]
        + [f"  - {line}   → {skill_for(line)}" for line in lines]
        + [
            "무인 실행이 자기 권한 밖이라 남긴 잔여 작업이다. "
            f"세션의 첫 응답에서 사용자에게 지금 처리할지 한 줄로 묻고, 승인하면 "
            f"{' · '.join(skills)} 로 처리한 뒤 해당 체크박스를 닫아라. "
            "승인 전에는 손대지 마라."
        ]
    )

    # ⚠️ SessionStart 훅은 **평문 stdout 이 컨텍스트에 실리지 않는다** (2026-08-26 실측:
    # 훅은 돌고 상태 파일도 써졌는데 세션은 "없음"이라고 답했다).
    # hookSpecificOutput.additionalContext 로 내보내야 주입된다.
    if hook_run:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "SessionStart",
                        "additionalContext": body,
                    }
                },
                ensure_ascii=False,
            )
        )
    else:
        print(body)  # 수동 실행 — 사람이 눈으로 보게

    if hook_run:
        mark_shown(today, digest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
