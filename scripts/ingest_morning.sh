#!/bin/bash
# 매일 08:00 launchd(com.user.wiki-ingest)가 부르는 무인 ingest — 규약 §6.2.
#
# 1~4단계(raw 이동 · 통독 · 배치 소스 페이지 · 등재)만 수행하고,
# 5단계(영향받는 기존 페이지 수정)는 사람이 "반영해줘" 라고 할 때 대화형으로 한다.
#
# ⚠️ 대상은 SessionEnd 훅이 만든 파일뿐이다. 사용자가 직접 넣은 파일은 손대지 않는다 —
#    어디서 온 무엇인지 물어야 하고, raw 는 불변이라 분류를 틀리면 정정이 번거롭다.
#
# 사용법:
#     ./scripts/ingest_morning.sh              # 실제 실행
#     ./scripts/ingest_morning.sh --dry-run    # 대상만 세고 종료 (claude 호출 없음)

set -u
# 자기 위치(볼트/scripts/)로 볼트를 찾는다. VAULT_PATH 로 덮어쓸 수 있다
VAULT="${VAULT_PATH:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$VAULT" || exit 1

# 훅 산출물만 센다. 없으면 토큰을 쓰지 않고 즉시 끝낸다
shopt -s nullglob
targets=(inbox/*-세션-*.md inbox/*-문서-*.md)
shopt -u nullglob

if [ ${#targets[@]} -eq 0 ]; then
    echo "[$(date '+%F %T')] 소화할 훅 산출물 없음 — 종료"
    exit 0
fi

echo "[$(date '+%F %T')] 훅 산출물 ${#targets[@]}건 발견"
printf '  %s\n' "${targets[@]}"

if [ "${1:-}" = "--dry-run" ]; then
    echo "(dry-run — claude 호출 없이 종료)"
    exit 0
fi

# ⚠️ launchd 는 셸 프로필을 읽지 않는다 — PATH 가 /usr/bin:/bin:/usr/sbin:/sbin 뿐이라
# `claude`(~/.local/bin)를 못 찾는다. 2026-08-26 까지 08:00 무인 ingest 가 대상이 있는
# 날에도 아무것도 소화하지 못한 원인이다 (사람이 셸에서 돌릴 때만 됐다).
#
# 두 겹으로 막는다:
# ① PATH 보강 — 이 세션 안에서 도는 **플러그인 훅**도 PATH 를 물려받는다. 보강 전에는
#    node 를 쓰는 훅이 `node: command not found` 로 죽었다 (2026-08-26 실측)
# ② claude 는 절대경로로 확정 — PATH 에 없더라도 도는 게 낫다
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
CLAUDE_BIN="${CLAUDE_BIN:-$(command -v claude || true)}"
for cand in "$HOME/.local/bin/claude" /opt/homebrew/bin/claude /usr/local/bin/claude; do
    [ -x "$CLAUDE_BIN" ] && break
    CLAUDE_BIN="$cand"
done
if [ ! -x "$CLAUDE_BIN" ]; then
    echo "[$(date '+%F %T')] ⚠️ claude 실행파일을 못 찾았다 — 중단 (CLAUDE_BIN 으로 지정 가능)"
    exit 127
fi
echo "[$(date '+%F %T')] claude: $CLAUDE_BIN"

# 이 세션 안에서 lint 를 돌릴 인터프리터. launchd 의 맨 PATH 에서 `python3` 는 시스템
# 파이썬(3.9)이라, plist 가 쓰는 것과 다른 인터프리터로 검증하게 된다. plist 가
# EnvironmentVariables 로 PYTHON_BIN 을 넘기면 그것을, 없으면 PATH 의 python3 를 쓴다
PY="${PYTHON_BIN:-python3}"
echo "[$(date '+%F %T')] python: $PY ($("$PY" -V 2>&1))"

# 이 세션은 사람이 안 보는 세션이다 — SessionStart 훅의 볼트 잔여 작업 알림을 재운다.
# 안 재우면 그 알림이 무인 ingest 컨텍스트로 들어가 소화 결과에 섞인다 (2026-08-26)
export VAULT_HOOK_SILENT=1

"$CLAUDE_BIN" -p "/wiki-ingest 무인 모드로 실행한다. 규약 docs/wiki-conventions.md §6.2 의 권한을 지켜라.

대상: inbox/ 의 훅 산출물(파일명에 -세션- 또는 -문서- 가 있는 것)만. 사용자가 직접 넣은
다른 파일은 읽지도 옮기지도 마라.

할 것: 세션 ID 단위로 묶어 1~4단계 — raw 채널로 이동(-세션-→conversations, -문서-→docs,
단 -wiki.md 제자리 덮어쓰기 예외가 우선), 원본 통독, wiki/1-sources/ 에 배치 소스 페이지
생성, index.md 등재, log.md 에 '## [날짜] ingest | 무인' 기록.

하지 말 것: 5단계(영향받는 기존 페이지 수정) 금지. 페이지 삭제 금지. inbox 파일 버리기 금지.
lesson confidence 변경 금지.

넘길 것: 5단계 후보를 볼트 루트의 **볼트-백로그.md** 에 체크박스 **한 줄**로 남겨라
(일지에는 쓰지 마라 — 일지 「볼트」 섹션은 폐지됐다. 상세는 log.md 에 적고
백로그엔 행동이 필요한 것만 한 줄) —
'- [ ] ingest(날짜): 세션 N건 소화됨 — [[배치 소스]] / 영향 후보: [[A]] · [[B]]'
같은 줄이 이미 있으면 중복 추가하지 마라.

마지막에 $PY scripts/lint_all.py 로 검증하고, 자기가 만진 파일만 'auto-ingest | 날짜' 로 커밋해라." \
    --permission-mode acceptEdits \
    --allowedTools "Bash($PY scripts/lint_all.py)" \
                   "Bash($PY scripts/lint_autofix.py:*)" \
                   "Bash(git add:*)" "Bash(git commit:*)" "Bash(git status:*)" \
                   "Bash(git mv:*)" "Bash(mv:*)" "Bash(ls:*)"

echo "[$(date '+%F %T')] 무인 ingest 종료 (exit $?)"
