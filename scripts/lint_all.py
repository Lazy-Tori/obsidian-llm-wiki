#!/usr/bin/env python3
"""lint 전종을 돌리고 실패한 검사만 요약한다. Lint 오퍼레이션의 기계 검사 단계 진입점.

`scripts/lint-*.py` 를 글롭해 실행하므로 **검사가 늘거나 줄어도 여기는 안 고친다** —
개수를 외워 적으면 조용히 낡는다 (2026-08-25 "lint 7종" 하드코딩을 걷어낸 이유).

각 검사는 문제가 있으면 exit 1 을 낸다. 이 러너는 그 코드를 모아 한 줄로 요약하고,
자신도 하나라도 실패하면 exit 1 을 낸다.

⚠️ **exit 0 이 "위키가 깨끗하다" 는 뜻은 아니다** — 아래 두 가지는 통과로 뜬다:
  - `lint-index-stats` 의 「대조 못 함」 (현황에 안 적힌 항목은 검사 자체가 불가)
  - allowlist 에 등록된 예약 링크
`--verbose` 로 전문을 보거나, 요약의 `주의` 줄을 읽는다.

사용법:
    python3 scripts/lint-all.py             # 요약
    python3 scripts/lint-all.py --verbose   # 실패한 검사의 전문까지
    python3 scripts/lint-all.py --json      # 전 검사 JSON 합본
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent


def run(path: Path, as_json: bool) -> tuple[int, str]:
    cmd = [sys.executable, str(path)] + (["--json"] if as_json else [])
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr)


def main() -> int:
    as_json = "--json" in sys.argv
    verbose = "--verbose" in sys.argv
    # 파일명에 하이픈이 없어 자기 자신은 글롭에 안 걸린다(lintlib.py 와 같은 규칙).
    # 그래도 이름을 바꿀 때 무한 재귀로 돌아가지 않도록 한 번 더 막는다
    checks = [
        p for p in sorted(SCRIPTS.glob("lint-*.py")) if p.name != Path(__file__).name
    ]

    results: list[tuple[str, int, str]] = []
    for path in checks:
        code, out = run(path, as_json)
        results.append((path.stem, code, out))

    failed = [name for name, code, _ in results if code != 0]

    if as_json:
        payload = []
        for name, code, out in results:
            try:
                payload.append(json.loads(out))
            except json.JSONDecodeError:
                # --json 을 모르는 검사(또는 크래시)는 원문 그대로 싣는다.
                # 조용히 빠뜨리면 러너가 검사를 삼킨 게 된다
                payload.append(
                    {"script": name, "ok": code == 0, "raw": out.strip(), "exit": code}
                )
        print(
            json.dumps(
                {"ok": not failed, "실패": failed, "검사": payload},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1 if failed else 0

    for name, code, out in results:
        print(f"{'FAIL' if code else ' ok '}  {name}")
        if code and verbose:
            print("\n".join("        " + ln for ln in out.strip().splitlines()))

    print(
        f"\n실패한 검사: {', '.join(failed) if failed else '없음'}  ({len(checks)}종 실행)"
    )
    print(
        "주의: exit 0 이어도 「대조 못 함」·allowlist 예약분은 검사 밖이다 — 전문을 볼 것"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
