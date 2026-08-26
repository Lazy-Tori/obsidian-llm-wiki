# 새 기기 세팅 — 볼트 밖에 사는 것들

이 볼트는 clone 만으로 완성되지 않는다. 아래 항목들은 **git 에 없거나 기기별 등록이
필요한 것들**이라, 기기를 바꾸면 이 문서대로 다시 세팅한다. (볼트 안 파일은 clone 이
가져오고, Obsidian 플러그인 목록은 `.obsidian/community-plugins.json` 으로 따라온다 —
여기 적는 건 그 바깥이다.)

## 1. 볼트 clone + Obsidian

```bash
git clone https://github.com/<계정>/<내볼트>.git ~/second-brain
export VAULT_PATH="$HOME/second-brain"   # 다른 경로에 뒀으면 여기서 알린다
```

- Obsidian 에서 「폴더를 보관함으로 열기」 → 볼트 폴더
- 스크립트는 **자기 위치(`볼트/scripts/`)로 볼트를 스스로 찾는다** — 환경변수 없이도 돈다.
  `VAULT_PATH` 는 스크립트를 볼트 밖에 두고 쓸 때의 덮어쓰기용이다.
  ⚠️ launchd·GUI 앱은 셸 프로필(`.zshrc`)을 읽지 않는다 — 아래 등록 스니펫이 **절대경로를
  파일에 박아 넣는** 이유다.
- 커뮤니티 플러그인: 제한 모드 해제 → 플러그인 파일은 아래 3·4번에서 복사

## 2. 전역 스킬 `wiki-*` (git 밖 — 2026-08-24 부터 전역 실파일)

스킬 실파일은 볼트의 `.claude/skills/wiki-*` 에 있다. 볼트 밖에서도 부르려면
홈으로 symlink 한다:

```bash
ln -sfn "$VAULT_PATH"/.claude/skills/wiki-* ~/.claude/skills/
```

볼트 안에서만 쓸 거면 이 단계는 필요 없다.

⚠️ **스킬은 스크립트와 달리 자기 위치로 볼트를 못 찾는다** — 볼트 밖에서 불리는 게 목적이라
경로를 알아야 하고, `VAULT="${VAULT_PATH:-$HOME/second-brain}"` 로 잡는다. 볼트를
`~/second-brain` 이 아닌 곳에 뒀으면 `VAULT_PATH` 를 셸 프로필에 넣거나(1번) 각
`SKILL.md` 의 그 줄을 자기 경로로 고친다. 안 하면 없는 경로를 보고 조용히 실패한다.

## 3. Obsidian 일반 플러그인 (obsidian-git · terminal · tasks)

`.obsidian/plugins/` 는 gitignore 라 clone 에 안 따라온다. 마켓에서 설치하거나
이전 기기에서 폴더째 복사:

```bash
rsync -a oldmac:"$VAULT_PATH"/.obsidian/plugins/ "$VAULT_PATH"/.obsidian/plugins/
```

## 4. (선택) 캘린더 연동 — CalDAV 플러그인

일지 「일정」 칸을 자동으로 채우고 싶을 때만 한다. 안 해도 나머지는 전부 돈다 —
`generate-daily.py` 는 `캘린더/YYYY-MM.md` 가 없으면 일정 없이 일지를 만든다.

CalDAV 를 읽어 `캘린더/YYYY-MM.md` 로 미러링하는 Obsidian 플러그인을 쓴다
(조직마다 다르므로 여기서는 지정하지 않는다). 설정할 값:

- Server URL: 쓰는 캘린더 서버의 CalDAV 주소
- Username / Password: 그 계정 (플러그인이 localStorage 에만 저장 — 기기마다 재입력)
- 캘린더 목록을 불러와 미러할 캘린더 선택

⚠️ `캘린더/` 는 `.gitignore` 대상이다 — 5분마다 재생성되므로 추적하면 커밋 노이즈가 되고,
일정이 원격 레포에 쌓인다.

## launchd 환경의 함정 (5·5.1·5.2 를 등록하기 전에 읽는다)

launchd 는 **셸 프로필을 읽지 않는다.** job 이 보는 것은
`PATH=/usr/bin:/bin:/usr/sbin:/sbin` 뿐이다. 그래서 **사람이 셸에서 돌려 성공한 것은
무인 실행의 검증이 아니다.** 실제로 이렇게 샜다 (2026-08-26):

- **`python3` 가 시스템 파이썬** — 셸에서 쓰는 것과 다른 인터프리터로 돈다. plist 에
  **인터프리터를 절대경로로 박는다**(아래 `$PY`). 무인 ingest 는 자기 세션 안에서 lint 를
  돌리므로 `EnvironmentVariables` 로 `PYTHON_BIN` 을 넘겨 같은 것을 쓰게 한다
- **`claude` 를 못 찾았다** — 무인 ingest 가 대상이 있는 날에도 아무것도 소화하지 못하고
  있었다. `ingest_morning.sh` 가 절대경로로 확정한다 (`CLAUDE_BIN` 으로 지정 가능)
- **세션 안에서 도는 플러그인 훅의 `node` 도 못 찾았다** — 같은 스크립트가 PATH 를 보강한다

무인 job 은 셸이 아니라 **`launchctl kickstart` 로 확인한다**:

```bash
launchctl kickstart -p gui/$(id -u) com.user.<label> && sleep 5 && cat /tmp/<label>.log
```

## 5. 일지 자동 생성 launchd (매일 07:00, 당일)

아래 5·5.1·5.2 는 **볼트 폴더 안에서** 실행한다 — `$VAULT` 가 plist 에 절대경로로 박힌다:

```bash
cd ~/second-brain && VAULT="$PWD"   # 자기 볼트 경로로
PY="$(command -v python3.12 || command -v python3)"   # 3.12+ 권장. plist 에 절대경로로 박힌다
```

스크립트는 볼트에 있고(`scripts/generate-daily.py`) **스케줄 등록만 기기별**이다:

```bash
cat > ~/Library/LaunchAgents/com.user.wiki-daily-gen.plist <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.user.wiki-daily-gen</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PY</string>
        <string>$VAULT/scripts/generate-daily.py</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key><integer>7</integer>
        <key>Minute</key><integer>0</integer>
    </dict>
    <key>RunAtLoad</key><false/>
    <key>StandardOutPath</key><string>/tmp/wiki-daily-gen.log</string>
    <key>StandardErrorPath</key><string>/tmp/wiki-daily-gen.log</string>
</dict>
</plist>
EOF
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.user.wiki-daily-gen.plist
```

관리:

```bash
launchctl list | grep wiki-daily                              # 등록 확인
launchctl kickstart gui/$(id -u)/com.user.wiki-daily-gen      # 즉시 실행 (테스트)
launchctl bootout gui/$(id -u)/com.user.wiki-daily-gen        # 해제
cat /tmp/wiki-daily-gen.log                                   # 마지막 실행 로그
```

## 5.1 위키 lint 자동 점검 launchd (매일 08:30)

스크립트는 볼트에 있고(`scripts/lint_morning.py`) **스케줄 등록만 기기별**이다.
정답이 하나뿐인 것만 고치고 나머지는 그날 일지 「볼트」로 넘긴다 (규약 §8.1):

```bash
cat > ~/Library/LaunchAgents/com.user.wiki-lint.plist <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.user.wiki-lint</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PY</string>
        <string>$VAULT/scripts/lint_morning.py</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict><key>Hour</key><integer>8</integer><key>Minute</key><integer>30</integer></dict>
    <key>RunAtLoad</key><false/>
    <key>StandardOutPath</key><string>/tmp/wiki-lint.log</string>
    <key>StandardErrorPath</key><string>/tmp/wiki-lint.log</string>
</dict>
</plist>
EOF
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.user.wiki-lint.plist
```

관리는 일지 생성기와 같다 (`launchctl list | grep wiki` · `kickstart` · `bootout`).
동작 확인은 `python3 scripts/lint_morning.py --dry-run` — 일지·log·커밋 없이 결과만 본다.

## 5.2 무인 ingest launchd (매일 08:00)

훅이 채운 `inbox/` 를 매일 아침 자동으로 비운다 — 1~4단계만 하고 5단계(기존 페이지 수정)는
사람이 "반영해줘" 할 때 대화형으로 (규약 §6.2). 점검(08:30)보다 **먼저** 돌아야 한다:

```bash
cat > ~/Library/LaunchAgents/com.user.wiki-ingest.plist <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.user.wiki-ingest</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$VAULT/scripts/ingest_morning.sh</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHON_BIN</key><string>$PY</string>
    </dict>
    <key>StartCalendarInterval</key>
    <dict><key>Hour</key><integer>8</integer><key>Minute</key><integer>0</integer></dict>
    <key>RunAtLoad</key><false/>
    <key>StandardOutPath</key><string>/tmp/wiki-ingest.log</string>
    <key>StandardErrorPath</key><string>/tmp/wiki-ingest.log</string>
</dict>
</plist>
EOF
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.user.wiki-ingest.plist
```

동작 확인은 `./scripts/ingest_morning.sh --dry-run` — 대상만 세고 claude 를 부르지 않는다.
훅 산출물이 없으면 토큰을 쓰지 않고 즉시 종료한다.

## 6. 세션 요약 훅 (SessionEnd → inbox)

어느 프로젝트든 Claude 세션이 끝나면 요약을 볼트 inbox 로 떨구는 훅.
스크립트는 볼트에 있고(`scripts/session-to-inbox.py`) **등록만 기기별**이다 —
`~/.claude/settings.json` 의 `hooks.SessionEnd` 에:

```json
{"hooks": [{"type": "command", "command": "python3 /Users/<계정>/<볼트>/scripts/session-to-inbox.py", "timeout": 20}]}
```

## 6.1 볼트 잔량 훅 (SessionStart → 미처리 알림)

무인 ingest·무인 점검이 자기 권한 밖이라 일지 「볼트」에 남긴 잔여 작업을, 세션이
열릴 때 컨텍스트로 올린다. `~/.claude/settings.json` 의 `hooks.SessionStart` 에
**두 군데** — `matcher: "startup"` 과 `matcher: "resume|clear"` — 로 등록한다
(`startup` 만 걸면 `--resume` 이나 `/clear` 로 이어간 세션에서 안 뜬다):

```json
{"type": "command", "command": "python3 /Users/<계정>/<볼트>/scripts/vault_backlog_hook.py", "timeout": 10}
```

세션 요약 훅과 같은 짝이다 — 끝날 때 inbox 로 넣고(§6), 열 때 잔량을 꺼낸다.
**보고만 하고 실행은 사람이 승인한 뒤** 대화형으로 한다 (규약 §6.2·§8.1 의 무인 권한
범위를 우회하지 않기 위해). 미처리가 없으면 침묵하고, 같은 잔량은 하루 1회만 알린다
(상태: `~/.claude/.vault-backlog-state.json` — 지우면 다시 알린다).

⚠️ **사람이 없는 세션에서는 침묵한다** — `claude -p`(entrypoint `sdk-cli`)이거나
`VAULT_HOOK_SILENT` 이 설정된 경우. 안 그러면 이 알림이 세션 요약기·무인 ingest 의
컨텍스트로 들어가 그 산출물에 섞인다 (2026-08-26 실측). 모르는 entrypoint 는 사람으로
취급한다 — 침묵이 기본값이 되면 알림이 조용히 죽는다.

## 7. 로컬 전용 raw 데이터

`raw/` 의 로컬 채널(conversations·notes·docs·personal·assets)과 `inbox/` 는
**git 에 없다** — 이전 기기에서 직접 옮겨야 한다:

```bash
rsync -a oldmac:"$VAULT_PATH"/raw/ "$VAULT_PATH"/raw/
rsync -a oldmac:"$VAULT_PATH"/inbox/ "$VAULT_PATH"/inbox/
```

⚠️ 이 데이터의 평시 백업은 Time Machine 뿐이다 — 새 기기에서 Time Machine 이
켜져 있는지 같이 확인할 것.

## 8. 확인

```bash
cd "$VAULT_PATH" && python3 scripts/lint_all.py                          # lint 전종
python3 scripts/generate-daily.py                                        # 일지 생성 동작
```
