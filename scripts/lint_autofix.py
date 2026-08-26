#!/usr/bin/env python3
"""lint 발견 중 **정답이 하나뿐인 것만** 고친다 (규약 §8.1).

무인 실행(매일 08:30)에서 쓰는 결정론적 수정기다. LLM 을 부르지 않는다 —
"그날 판단이 달랐다" 가 불가능해야 무인 수정을 신뢰할 수 있기 때문이다.

고치는 것 (문장을 쓰지 않고, 되돌리기 쉬운 것):
  1. 낡은 allowlist 항목 제거 — 대상 페이지가 실제로 생긴 예약
  2. `index.md` 「현황」 숫자 동기화 — **등재 누락이 없을 때만** (아래 ⚠️)
  3. 프론트매터 `updated` 누락 보정 — git 마지막 커밋 날짜

고치지 않는 것 (문장·의도 판단이 필요 — 일지 「이슈」로 넘긴다):
  고아 페이지 · 깨진 링크 · 이름 충돌 · index 목록 등재 누락 ·
  lesson 하향 · 신선도 · raw 미소화 · 모순/승격 후보 같은 의미 검사

⚠️ **숫자만 고치면 은폐가 된다.** 현황 숫자가 어긋나는 흔한 원인은 "페이지를 만들고
index 목록에 안 넣었다" 이고, 숫자 불일치가 그 누락을 알려주는 **유일한 신호**다.
그래서 목록에 빠진 페이지가 하나라도 있으면 숫자 동기화를 **거부**하고 이슈로 넘긴다.
카탈로그 한 줄 요약은 내용이라 기계가 쓸 수 없다.

사용법:
    python3 scripts/lint-autofix.py            # 수정 적용
    python3 scripts/lint-autofix.py --dry-run  # 무엇을 고칠지만 출력
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
INDEX = ROOT / "index.md"
ALLOWLIST = SCRIPTS / "lint-allowlist.txt"

sys.path.insert(0, str(SCRIPTS))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(
        name.replace("-", "_"), SCRIPTS / f"{name}.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


lint_links = _load("lint-links")
lint_stats = _load("lint-index-stats")

FM = re.compile(r"---\n(.*?)\n---", re.DOTALL)


def unlisted_pages() -> list[str]:
    """`index.md` 목록에 안 걸린 위키 페이지 — 숫자 동기화의 차단 조건."""
    pages, links, _ = lint_links.collect()
    from_index = {t for t, srcs in links.items() if "index.md" in srcs}
    out = []
    for name, path in pages.items():
        if name in lint_links.NOT_A_PAGE or lint_links.DATED_PAGE.match(name):
            continue  # 관리 파일·일지는 카탈로그 대상이 아니다 (일지 제외는 규약 §11)
        if not str(path).startswith(str(ROOT / "wiki")):
            continue
        if name not in from_index:
            out.append(name)
    return sorted(out)


def fix_allowlist(dry: bool) -> list[str]:
    """대상이 생긴 예약 항목을 목록에서 뺀다. 목록은 자라기만 해서는 안 된다."""
    if not ALLOWLIST.exists():
        return []
    pages, _, _ = lint_links.collect()
    kept, removed = [], []
    for line in ALLOWLIST.read_text(encoding="utf-8").splitlines():
        name = line.split("#", 1)[0].strip()
        if name and name in pages:
            removed.append(name)
            continue
        kept.append(line)
    if removed and not dry:
        ALLOWLIST.write_text("\n".join(kept) + "\n", encoding="utf-8")
    return [f"allowlist 에서 제거 (대상이 생김): {n}" for n in removed]


def fix_index_numbers(dry: bool) -> tuple[list[str], list[str]]:
    """「현황」 숫자를 실제 집계로 맞춘다. 등재 누락이 있으면 거부하고 이슈로 넘긴다."""
    missing = unlisted_pages()
    if missing:
        return [], [
            f"index.md 목록에 없는 페이지 {len(missing)}건 — 등재가 먼저다 "
            f"(숫자만 고치면 이 누락이 은폐된다): {', '.join(missing)}"
        ]

    text = INDEX.read_text(encoding="utf-8")
    have = lint_stats.actual()
    want = lint_stats.declared(text)
    diffs = {k: have[k] for k in want if k in have and want[k] != have[k]}

    # inbox 는 숫자만 바꾸면 뒤의 서술이 거짓말이 되므로 **줄 전체를 정해진 두 형식 중
    # 하나로 다시 쓴다** (2026-08-26 변경). 전에는 자동 수정을 거부하고 이슈로 넘겼는데,
    # ① 잔량이 0인데 현황이 4일 때 "0건 미처리 — 소화가 밀렸다"는 헛소리를 만들었고
    # ② 숫자를 맞춰도 백로그는 오히려 더 잘 보인다(은폐가 아니라 사실 반영).
    # 문장을 짓는 게 아니라 두 템플릿 중 하나를 고르는 것이라 "기계는 형태만" 을 지킨다.
    inbox_n = diffs.pop("inbox", None)
    deferred = []
    if inbox_n is not None:
        text_now = INDEX.read_text(encoding="utf-8")
        today = date.today().isoformat()
        new_line = (
            f"- inbox: 0개 — 소화 완료({today})"
            if inbox_n == 0
            else f"- inbox: {inbox_n}개 — 미처리"
        )
        patched, n = re.subn(r"^- inbox:.*$", new_line, text_now, count=1, flags=re.M)
        if n:
            if not dry:
                INDEX.write_text(patched, encoding="utf-8")
            fixed_inbox = [f"현황 inbox 줄 갱신 → {new_line[2:]}"]
        else:
            fixed_inbox = []
            deferred.append("index.md 「현황」에 inbox 줄이 없다 — 사람이 볼 것")
        if inbox_n:
            deferred.append(f"inbox 미처리 {inbox_n}건 — 소화가 밀렸다 (ingest 필요)")
    else:
        fixed_inbox = []

    if not diffs:
        return fixed_inbox, deferred

    block_re = re.compile(r"^## 현황$(.*?)(?=^---|\Z)", re.M | re.DOTALL)
    m = block_re.search(text)
    if not m:
        return [], ["index.md 「현황」 블록을 못 찾음 — 사람이 볼 것"]
    block = m.group(1)

    # lint-index-stats.declared() 와 **같은 패턴**으로 되짚어 쓴다.
    # 사본을 두면 읽기와 쓰기가 갈리므로 그쪽 정규식을 그대로 재사용한다
    patterns = {
        "페이지": r"(\*\*)(\d+)(\s*페이지\*\*)",
        "링크": r"(링크\s+)(\d+)(개)",
        "깨진 링크": r"(깨진 링크\s+)(\d+)",
        "고아": r"(고아\s+)(\d+)",
        # inbox 는 위에서 걸러 여기 오지 않는다 (뒤 서술이 딸린 줄이라 숫자만 못 고침)
    }
    for label in lint_stats.TYPE_LABEL.values():
        patterns[label] = rf"({label}\s+)(\d+)"
    for c in lint_stats.CONFIDENCE_ORDER:
        patterns[c] = rf"({c}\s+)(\d+)"

    changed = []
    for key, value in diffs.items():
        pat = patterns.get(key)
        if not pat:
            continue
        new_block, n = re.subn(
            pat,
            lambda mo: (
                f"{mo.group(1)}{value}{mo.group(3) if mo.lastindex and mo.lastindex >= 3 else ''}"
            ),
            block,
            count=1,
        )
        if n:
            changed.append(f"현황 숫자 {key}: {want[key]} → {value}")
            block = new_block
    if changed and not dry:
        INDEX.write_text(
            text[: m.start(1)] + block + text[m.end(1) :], encoding="utf-8"
        )
    return fixed_inbox + changed, deferred


def git_date(path: Path) -> str:
    p = subprocess.run(
        ["git", "log", "-1", "--format=%ad", "--date=short", "--", str(path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return p.stdout.strip()


def fix_missing_updated(dry: bool) -> list[str]:
    """`updated` 누락을 git 마지막 커밋 날짜로 채운다. 없으면 건너뛴다(추측하지 않는다)."""
    done = []
    for path in sorted(ROOT.glob("wiki/**/*.md")):
        text = path.read_text(encoding="utf-8")
        if text.startswith("> 회사 위키 문서 원본"):
            continue
        m = FM.match(text)
        if not m or re.search(r"^updated:[ \t]*\S", m.group(1), re.M):
            continue
        stamp = git_date(path)
        if not stamp:
            continue  # 커밋된 적 없는 파일 — 날짜를 지어내지 않는다
        fm = m.group(1)
        if re.search(r"^updated:", fm, re.M):
            new_fm = re.sub(
                r"^updated:.*$", f"updated: {stamp}", fm, count=1, flags=re.M
            )
        else:
            new_fm = fm + f"\nupdated: {stamp}"
        if not dry:
            path.write_text(text.replace(fm, new_fm, 1), encoding="utf-8")
        done.append(f"{path.stem}: updated 보정 → {stamp}")
    return done


def main() -> int:
    dry = "--dry-run" in sys.argv
    fixed: list[str] = []
    deferred: list[str] = []

    fixed += fix_allowlist(dry)
    nums, blocked = fix_index_numbers(dry)
    fixed += nums
    deferred += blocked
    fixed += fix_missing_updated(dry)

    print(f"=== 자동 수정{' (dry-run)' if dry else ''} ===\n")
    if fixed:
        for f in fixed:
            print(f"  ✔  {f}")
    else:
        print("  고칠 것 없음")
    if deferred:
        print("\n  [자동 수정 거부 — 사람 판단 필요]")
        for d in deferred:
            print(f"  ⚠️   {d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
