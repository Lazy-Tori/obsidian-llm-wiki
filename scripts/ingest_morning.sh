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

claude -p "/wiki-ingest 무인 모드로 실행한다. 규약 docs/wiki-conventions.md §6.2 의 권한을 지켜라.

대상: inbox/ 의 훅 산출물(파일명에 -세션- 또는 -문서- 가 있는 것)만. 사용자가 직접 넣은
다른 파일은 읽지도 옮기지도 마라.

할 것: 세션 ID 단위로 묶어 1~4단계 — raw 채널로 이동(-세션-→conversations, -문서-→docs,
단 -wiki.md 제자리 덮어쓰기 예외가 우선), 원본 통독, wiki/1-sources/ 에 배치 소스 페이지
생성, index.md 등재, log.md 에 '## [날짜] ingest | 무인' 기록.

하지 말 것: 5단계(영향받는 기존 페이지 수정) 금지. 페이지 삭제 금지. inbox 파일 버리기 금지.
lesson confidence 변경 금지.

넘길 것: 5단계 후보를 오늘 일지 wiki/daily/<오늘>.md 의 **「볼트」 섹션**에 체크박스 **한 줄**로 남겨라 (「이슈」는 사람의 업무 이슈 전용이라 쓰지 마라. 상세는 log.md 에 적고 일지엔 행동이 필요한 것만 한 줄) —
'- [ ] ingest(날짜): 세션 N건 소화됨 — [[배치 소스]] / 영향 후보: [[A]] · [[B]]'
같은 줄이 이미 있으면 중복 추가하지 마라.

마지막에 python3 scripts/lint_all.py 로 검증하고, 자기가 만진 파일만 'auto-ingest | 날짜' 로 커밋해라." \
    --permission-mode acceptEdits \
    --allowedTools "Bash(python3 scripts/lint_all.py)" \
                   "Bash(python3 scripts/lint_autofix.py:*)" \
                   "Bash(git add:*)" "Bash(git commit:*)" "Bash(git status:*)" \
                   "Bash(git mv:*)" "Bash(mv:*)" "Bash(ls:*)"

echo "[$(date '+%F %T')] 무인 ingest 종료 (exit $?)"
