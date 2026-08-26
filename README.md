# obsidian-llm-wiki — LLM Wiki 볼트 껍데기

Obsidian + Claude Code 로 **세컨드 브레인**을 운영하기 위한 구조 템플릿.
내용은 비어 있다 — 폴더 골격, 규약, 페이지 템플릿, 점검 스크립트, 오퍼레이션 스킬만 들어 있다.

[LLM Wiki 패턴](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)을
개인 경험 기록용으로 좁혀 실제로 운영한 뒤, 데이터를 빼고 구조만 추출한 것이다.

## 무엇이 다른가

RAG 는 질문마다 원본을 다시 검색한다. **어제 한 종합이 오늘 남지 않는다.**
이 구조는 LLM 이 한 번 정리해 위키를 만들고 유지보수까지 맡는다 — 지식을 컴파일해 둔다.

핵심은 폴더가 아니라 **승격**이다:

```
근거(source·experiment·대화) ──(독립 근거 2건)──▶ lesson
```

이게 없으면 그냥 일지가 된다.

## 3계층 — 누가 무엇을 소유하는가

| 계층 | 위치 | 소유 | 규칙 |
|---|---|---|---|
| 원본 | `raw/` | 사람 | **불변.** LLM 은 읽기만 한다 |
| 위키 | `wiki/` | LLM | LLM 이 만들고 고친다. 사람은 주로 읽는다 |
| 규약 | `CLAUDE.md` · `docs/` · `templates/` · `scripts/` | 공동 | 안 맞으면 고친다 |

## 폴더

```
inbox/         모든 입력의 1차 착지 — 판단 0으로 던져둔다. 비우는 게 ingest
raw/           원본 (불변) — 취급 방식으로 나눈다
  conversations/  대화 발췌        notes/     내가 쓴 메모
  docs/           외부 문서 사본    personal/  민감 기록 (credentials/ = ingest 비대상)
  external/       외부 공개물 — git 추적하는 유일한 채널 (논문은 papers/)
  assets/         이미지·첨부
wiki/
  1-sources/ 1-experiments/ 2-lessons/          ← 승격 사다리 (같은 층 = 같은 번호)
  concepts/ projects/ builds/ daily/ questions/ ← 사다리 밖
index.md       카탈로그 — LLM 이 답하기 전에 먼저 읽는다
log.md         시간순 기록 (append-only)
templates/     페이지 템플릿 8종
scripts/       점검 스크립트 + 자동화
```

## 오퍼레이션 스킬 6종

| 스킬 | 언제 |
|---|---|
| `wiki-ingest` | 자료를 넣을 때. **inbox 를 비우는 것이 이 스킬** |
| `wiki-query` | 위키에 물어볼 때. 근거 페이지를 링크로 달아 답한다 |
| `wiki-daily` | 그날 업무 일지 |
| `wiki-lint` | 점검. 기계 검사 + 의미 검사 |
| `wiki-challenge` | 내 아이디어를 위키의 기록으로 **반박**받을 때 |
| `wiki-emerge` | 아직 이름 없는 반복 패턴을 찾을 때 |

스킬은 절차의 **사본이 아니라 진입점**이다 — 원문은 `CLAUDE.md` 에 있고 스킬이 그걸 읽고
따른다. 복사해 두면 규약을 고칠 때 스킬이 낡은 절차를 시킨다.

## clone 하면 어디까지 되나

|  | clone 직후 | 따로 세팅 |
|---|---|---|
| 폴더 골격 · 규약 · 템플릿 · 스크립트 | ✅ 그대로 | — |
| 스킬 | ✅ **볼트 폴더 안에서** 바로 (프로젝트 스킬로 잡힌다) | 볼트 밖에서도 부르려면 **전역 등록** (설치 2번) |
| 훅 · 자동화(launchd) | ❌ **하나도 안 돈다** | `docs/machine-setup.md` 보고 각자 등록 |

스크립트는 자기 위치로 볼트를 찾으므로 `python3 scripts/lint_all.py` 는 clone 직후 그냥 돈다.
**안 따라오는 것은 "언제 부를지"** 다 — 훅 등록(`~/.claude/settings.json`)과 스케줄
(`~/Library/LaunchAgents/`)은 볼트 밖에 살아서 git 에 담기지 않는다.

## 설치

**1. 볼트 만들기** — GitHub 에서 **「Use this template」** 로 새 레포를 만든다.
**반드시 Private** — 위키에 개인·업무 내용이 쌓인다.

```bash
git clone https://github.com/<내계정>/<내볼트>.git ~/second-brain
```

Obsidian 에서 「폴더를 보관함으로 열기」.

**2. 스킬 전역 등록** — 어느 디렉토리에서든 `/wiki-ingest` 가 잡히게:

```bash
cd ~/second-brain
ln -sfn "$PWD"/.claude/skills/wiki-* ~/.claude/skills/
```

볼트 안에서만 쓸 거면 건너뛰어도 된다 — `.claude/skills/` 에 이미 있다.
스크립트는 자기 위치로 볼트를 찾으므로 경로 설정이 필요 없지만, **스킬은 다르다** —
전역 등록한 스킬은 볼트 밖에서도 불리므로 볼트 경로를 알아야 한다. 기본값이
`~/second-brain` 이니 **다른 경로에 뒀으면 셸 설정에 알린다**:

```bash
echo 'export VAULT_PATH="$HOME/my-vault"' >> ~/.zshrc   # 자기 경로로
```

**3. Obsidian 플러그인 3개** (설치 후 **활성화까지**)

- **Git** — 버전 관리·백업
- **Terminal** — 볼트 안에서 Claude Code 실행
- **Tasks** — 일지 체크박스 (완료 취소선 스니펫이 이걸 전제한다)

**4. (선택) Web Clipper** — 노트 이름 `{{date|date:"YYMMDD"}}-{{title}}`,
저장 위치 `raw/external`(논문은 `raw/external/papers`).
git 은 파일 수정시각을 보존하지 않으므로 **날짜는 파일명에 남겨야 남는다.**

**5. (선택) 자동화 등록** — 아래 「자동화」 참고. `docs/machine-setup.md` 에 절차가 있다.

**6. `CLAUDE.md` 를 내 목적에 맞게 깎는다** — 가장 중요하다.
이 템플릿의 규약은 "시도 → 경험 → 배움 → 산출물"을 축으로 좁혀져 있다.
축이 다르면 페이지 타입부터 바꿔야 한다.

## 자동화 — 사람이 안 불러도 도는 것

기억력에 기대면 절차는 샌다. 그래서 **부르지 않아도 도는 것**을 따로 둔다.

⚠️ **아래 표는 clone 직후엔 하나도 돌지 않는다.** 등록 절차(launchd·Claude Code 훅)는
기기별이라 git 에 안 따라온다 — 스크립트만 따라오고, 켜는 것은 `docs/machine-setup.md`.

| 언제 | 무엇 |
|---|---|
| 매일 07:00 | 일지 생성 (`generate-daily.py`) — 일정 · 미완료 이월 · 예약 주입 |
| 매일 08:00 | 무인 ingest (`ingest_morning.sh`) — inbox 를 1~4단계만 소화 |
| 매일 08:30 | 위키 점검 (`lint_morning.py`) — 자동 수정 3종 + 나머지는 일지 「볼트」로 |
| 세션 시작마다 | 일지 「볼트」 미처리를 올려 처리할지 묻는다 (`vault_backlog_hook.py`) |
| 세션 종료마다 | 세션 요약을 `inbox/` 로 (`session-to-inbox.py`) |

**무인 실행은 기존 페이지를 고치지 않는다.** 정답이 하나뿐인 것만 손대고, 판단이 필요한
몫은 그날 일지 「볼트」 섹션에 남긴다 — 다음에 세션을 열 때 훅이 그걸 다시 꺼낸다.
기계가 문장을 짓기 시작하면 위키를 믿을 수 없게 되기 때문이다.

## 점검

```bash
python3 scripts/lint_all.py            # 전종 실행, 실패한 것만 요약
python3 scripts/lint_all.py --verbose  # 실패한 검사의 전문까지
```

`scripts/lint-*.py` 를 글롭해 돌기 때문에 **검사를 추가해도 실행 목록은 저절로 맞는다.**

- **깨진 것**: 링크(깨짐·고아·이름 충돌) · 역링크 · 프론트매터
- **조용히 낡는 것**: 현황 숫자 · 사실 신선도 · lesson 방치 · raw 커버리지

뒤쪽이 진짜 가치다. 썩은 사실도 문장은 그대로라 **참처럼 읽히기** 때문이고,
그래서 이 검사들은 전부 사람이 우연히 사고를 발견한 뒤에야 만들어졌다.

⚠️ **exit 0 이 "깨끗함"은 아니다** — 예약 링크(`scripts/lint-allowlist.txt` 등록분)와
현황에 안 적힌 항목은 검사 밖이다. 요약만 보지 말고 출력을 읽는다.

## 주의

- **Obsidian 탐색기에서 `scripts/` 가 비어 보인다** — 마크다운이 아닌 파일을 기본 설정이
  숨긴다 (`.claude/` 도 마찬가지). 빈 폴더가 아니니 지우지 말 것.
  설정 → 파일 및 링크 → 「모든 파일 확장자 감지」로 볼 수 있다.
- **공개 경계는 폴더가 정한다.** `raw/external` 만 git 추적, 나머지 raw 는 전부 로컬.
  파일별로 판단하는 구조면 실수 하나가 유출이 된다.
- **자격증명 값을 `wiki/` 에 옮기지 않는다.** 원본에 있어도 "여기에 있다"만 적는다.
  git 이력에 한 번 들어가면 지우기 어렵다.
- **`raw/` 는 수정·삭제하지 않는다.** 진실의 출처가 흔들리면 위키 전체를 믿을 수 없게 된다.

## 라이선스

MIT. 구조를 가져가 각자 목적에 맞게 깎아 쓰면 된다.
