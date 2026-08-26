#!/usr/bin/env python3
"""위키링크 무결성 검사.

깨진 링크·고아 페이지·이름 충돌을 보고한다. CLAUDE.md 의 Lint 오퍼레이션에서 기계적으로
잡을 수 있는 항목을 담당한다. 모순·노후 판단처럼 의미를 읽어야 하는 항목은 LLM 이 직접 본다.

검사 항목:
  - 깨진 링크   : 대상 페이지가 없는 링크. **allowlist 에 없으면 실패**(2026-08-25 변경)
  - 고아 페이지 : 인바운드 링크가 없는 페이지 (일지는 면제 — 아래)
  - 이름 충돌   : 같은 파일명(stem)이 둘 이상 (2026-08-25 추가)
  - 안 걸린 일지: 아웃바운드 링크가 하나도 없는 과거 일지

⚠️ **깨진 링크는 2026-08-25 까지 실패로 치지 않았다.** "아직 안 쓴 페이지에 대한 예약일 수
있다" 는 이유였는데, 그 면제가 예약과 오타를 구분하지 않아 **오타 링크도 영원히 조용했다.**
이제 예약은 `scripts/lint-allowlist.txt` 에 명시적으로 등록하고, 등록 안 된 깨진 링크는
실패다 — 면제하려면 이름을 적어야 한다(적는 순간 그게 예약이라는 선언이 된다).

⚠️ **이름 충돌은 위키링크의 조용한 오배송이다.** 링크는 경로를 안 쓰고 파일명으로만 걸리므로
(CLAUDE.md 「페이지 규약 요약」), 같은 이름이 둘이면 [[X]] 가 어디로 가는지 아무도 모른다.
이 스크립트의 `pages` 딕셔너리도 나중 것이 앞의 것을 덮어써 **한쪽이 통째로 안 보이게 된다** —
검사기 자신이 조용히 눈이 머는 지점이라 별도 항목으로 잡는다.

사용법:
    python3 scripts/lint-links.py
    python3 scripts/lint-links.py --json    # 기계 판독용
"""

from __future__ import annotations

import collections
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lintlib import emit, strip_code, wants_json  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SCANNED = ["wiki/**/*.md", "index.md", "log.md", "CLAUDE.md"]
# 링크 대상이 아닌 관리 파일 — 고아 판정에서 제외한다
NOT_A_PAGE = {"index", "log", "CLAUDE"}
# 일지는 날짜로 찾는 페이지라 인바운드 링크를 요구하지 않는다. 대신 **아웃바운드**를
# 요구한다 — 어느 프로젝트·산출물에도 안 닿는 일지는 위키 노드가 아니라 일기다.
DATED_PAGE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# 인라인 코드·코드 블록 안의 [[...]] 는 문법 예시라 링크로 세지 않는다 — 제거는
# lintlib.strip_code() 가 한다 (전에는 이 정규식이 세 스크립트에 복붙돼 있었다)
WIKILINK = re.compile(r"\[\[([^\]|#]+)")

ALLOWLIST = ROOT / "scripts" / "lint-allowlist.txt"


def allowlisted() -> set[str]:
    """의도적으로 비워 둔 링크 대상 (아직 안 쓴 페이지에 대한 예약).

    한 줄에 대상 하나. `#` 뒤는 주석. 파일이 없으면 빈 집합 — 그러면 모든 깨진 링크가 실패다.
    """
    if not ALLOWLIST.exists():
        return set()
    out = set()
    for line in ALLOWLIST.read_text(encoding="utf-8").splitlines():
        name = line.split("#", 1)[0].strip()
        if name:
            out.add(name)
    return out


def collect() -> tuple[dict[str, Path], dict[str, set[str]], dict[str, set[str]]]:
    files: list[Path] = []
    for pattern in SCANNED:
        files.extend(ROOT.glob(pattern))

    pages = {f.stem: f for f in files}
    links: dict[str, set[str]] = {}
    outbound: dict[str, set[str]] = {}
    for f in files:
        text = f.read_text(encoding="utf-8")
        # 회사 위키 문서 원본(외부 시스템 미러) — 위키링크가 아니라 프로젝트 페이지의
        # 마크다운 링크로 참조되는 첨부물이라 승격 사다리의 "페이지"가 아니다.
        if text.startswith("> 회사 위키 문서 원본"):
            del pages[f.stem]
            continue
        for target in WIKILINK.findall(strip_code(text)):
            name = target.strip()
            links.setdefault(name, set()).add(f.name)
            outbound.setdefault(f.stem, set()).add(name)
    return pages, links, outbound


def duplicate_stems() -> dict[str, list[str]]:
    """같은 파일명이 둘 이상인 경우. 링크가 경로를 안 쓰므로 곧 오배송이다."""
    seen: dict[str, list[str]] = collections.defaultdict(list)
    for pattern in SCANNED:
        for f in ROOT.glob(pattern):
            text = f.read_text(encoding="utf-8")
            if text.startswith("> 회사 위키 문서 원본"):
                continue
            seen[f.stem].append(str(f.relative_to(ROOT)))
    return {stem: sorted(v) for stem, v in seen.items() if len(v) > 1}


def main() -> int:
    as_json = wants_json()
    pages, links, outbound = collect()
    reserved = allowlisted()

    broken_all = {t: src for t, src in links.items() if t not in pages}
    broken = {t: s for t, s in broken_all.items() if t not in reserved}
    reserved_hit = {t: s for t, s in broken_all.items() if t in reserved}
    # 대상이 생겼는데 allowlist 에 남아 있는 항목 — 예약이 이행됐으니 목록에서 빼야 한다.
    # 안 빼면 allowlist 가 자라기만 하고 아무것도 안 지키는 목록이 된다
    stale_allow = sorted(t for t in reserved if t in pages)
    dupes = duplicate_stems()

    orphans = [
        n
        for n in pages
        if n not in links and n not in NOT_A_PAGE and not DATED_PAGE.match(n)
    ]
    # 일지의 반대 검사: 아웃바운드가 하나도 없으면 위키에 안 걸린 기록이다.
    # 면제 2종 (2026-08-24, scripts/generate-daily.py):
    #   ① 오늘 이후 일지 — 아직 살지 않은 날의 자동 골격
    #   ② 골격 그대로인 과거 일지 — 작업·정해진 것·이슈가 비어 있으면 캘린더
    #     스냅샷일 뿐이라 연결을 요구하지 않는다. 내용을 채웠는데 안 이은 것만 잡는다.
    import re as _re
    from datetime import date

    today = date.today().isoformat()

    def skeleton_only(name: str) -> bool:
        text = pages[name].read_text(encoding="utf-8")
        for sec in ("작업", "정해진 것", "이슈"):
            m = _re.search(rf"## {sec}\n(.*?)(?=\n## |\Z)", text, _re.DOTALL)
            if m and m.group(1).strip():
                return False
        return True

    #   ③ 볼트 탄생(2026-08-24) 전 소급 일지 — 연결할 페이지들이 아직 구볼트에서
    #     이관되지 않았다. 이관이 끝나면 이 면제를 제거하고 링크를 건다.
    VAULT_BIRTH = "2026-08-24"
    lonely_dailies = sorted(
        n
        for n in pages
        if DATED_PAGE.match(n)
        and VAULT_BIRTH <= n < today
        and not (outbound.get(n, set()) & set(pages))
        and not skeleton_only(n)
    )

    wiki_pages = len(list(ROOT.glob("wiki/**/*.md")))
    total_links = sum(len(v) for v in links.values())
    failed = bool(broken or orphans or lonely_dailies or dupes or stale_allow)

    if as_json:
        return emit(
            "lint-links",
            not failed,
            {
                "깨진 링크": {t: sorted(s) for t, s in sorted(broken.items())},
                "이름 충돌": dupes,
                "고아": sorted(str(pages[n].relative_to(ROOT)) for n in orphans),
                "안 걸린 일지": lonely_dailies,
                "낡은 allowlist": stale_allow,
            },
            stats={"페이지": wiki_pages, "링크": total_links},
            예약된_링크={t: sorted(s) for t, s in sorted(reserved_hit.items())},
        )

    print("=== 깨진 링크 (대상 페이지 없음 · allowlist 미등록) ===")
    if broken:
        for target, sources in sorted(broken.items()):
            print(f"  ⚠️   [[{target}]]  ← {', '.join(sorted(sources))}")
        print(f"   → 오타면 고치고, 쓸 예정이면 {ALLOWLIST.name} 에 등록한다")
    else:
        print("  없음")

    if reserved_hit:
        print("\n=== 예약된 링크 (allowlist 등록분 — 통과) ===")
        for target, sources in sorted(reserved_hit.items()):
            print(f"  [[{target}]]  ← {', '.join(sorted(sources))}")
    if stale_allow:
        print("\n=== 낡은 allowlist 항목 (대상이 생겼다 — 목록에서 뺄 것) ===")
        for target in stale_allow:
            print(f"  ⚠️   {target}")

    print("\n=== 이름 충돌 (같은 파일명 — 링크가 어디로 갈지 모른다) ===")
    if dupes:
        for stem, paths in sorted(dupes.items()):
            print(f"  ⚠️   [[{stem}]] → {' · '.join(paths)}")
    else:
        print("  없음")

    print("\n=== 고아 페이지 (인바운드 링크 없음) ===")
    if orphans:
        for name in sorted(orphans):
            print(f"  {pages[name].relative_to(ROOT)}")
    else:
        print("  없음")

    print(f"\n페이지 {wiki_pages}개 · 링크 {total_links}개")

    print("\n=== 위키에 안 걸린 일지 (아웃바운드 링크 없음) ===")
    if lonely_dailies:
        for name in lonely_dailies:
            print(
                f"  {name}  ← 프로젝트·산출물 어디에도 안 닿는다 (일기지 위키 노드가 아니다)"
            )
    else:
        print("  없음")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
