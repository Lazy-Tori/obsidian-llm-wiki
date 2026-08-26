#!/usr/bin/env python3
"""Claude Code SessionEnd hook — 세션의 작업 내용을 볼트 inbox/ 에 구체적으로 남긴다.

어느 프로젝트에서 작업했든, 세션이 끝나면 그 세션에서 **실제로 한 일**을
볼트의 inbox/ 에 md 로 남긴다. inbox 는 "판단 0 착지" 버퍼라서 이 자동
투입과 정확히 맞는 자리다 — 소화(일지·프로젝트·build 반영)는 wiki-daily/ingest 가 한다.

두 단계로 돈다 (훅 타임아웃 20초를 넘기지 않기 위해):
1. 훅 본체 — 즉시 목차 파일을 쓴다: 메타 · 사용자 요청 1줄 전량 · 수정 파일 ·
   transcript 경로. 세션이 수정한 **.md·코드 파일(COPY_EXT)은 원문 그대로 inbox 에 복사**한다
   — 사용자가 중요한 내용을 마크다운 문서로 직접 만들어 두는 경우가 많고, 코드 변경도
   세션 요약(모델이 쓴 산문)만으론 정확한 원문이 이 볼트에 안 남기 때문. 코드는 펜스
   코드블록으로 감싸 저장한다. 그리고 2단계를 **분리된 백그라운드 프로세스**로 띄우고 끝난다.
2. `--summarize` — 다음을 전부 모아 `claude -p` 로 위키 타입별 착지 초안을 만든다:
   - 대화(사용자·어시스턴트 텍스트) + 툴 활동(Edit/Write 디프, Bash 명령·출력 등) 시간순
   - **세션이 수정한 파일의 현재 전문** (종료 시점에 새로 읽음 — 최종 상태가 진실)
   - 볼트 index.md 의 프로젝트·빌드·실험 목록 (소속을 찍기 위해)
   입력이 모델 한도를 넘으면 **앞을 버리지 않고** 시간순 청크로 나눠 각각 요약한 뒤
   통합한다 — 어느 구간도 무시되지 않게. 실패해도 목차 파일은 남는다.

- stdin 으로 hook JSON({session_id, transcript_path, cwd, reason})을 받는다.
- 볼트 자신에서의 세션은 건너뛴다 (산출물이 이미 볼트에 있다).
- 사용자 발화가 없는 세션(자동 실행 등)도 건너뛴다.
- 민감 경로(raw/personal, credentials, .env, 키 파일)는 요약 모델에 넘기지 않는다.
- 파일명에 session_id 를 넣어 멱등 — 같은 세션이 여러 번 끝나도 1파일.
- 실패해도 조용히 종료한다 (exit 0) — 훅이 세션 종료를 막으면 안 된다.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# 이 스크립트는 볼트 안(scripts/)에 살므로 자기 위치로 볼트를 찾는다 —
# 훅은 임의의 디렉토리에서 불리기 때문에 cwd 에 기댈 수 없다.
# 심볼릭 링크 등으로 밖에 두고 쓸 때만 VAULT_PATH 로 덮어쓴다.
VAULT = Path(
    os.environ.get("VAULT_PATH") or Path(__file__).resolve().parent.parent
).expanduser()
INBOX = VAULT / "inbox"
INDEX = VAULT / "index.md"
LINE_MAX = 120  # 요청 목차는 첫 줄 120자로 압축 — 원문은 transcript 에 있다
SUMMARY_MODEL = "sonnet"
CHUNK_CHARS = 350_000  # 모델 1회 입력 상한(문자). 넘으면 청크 요약 → 통합
TOOL_RESULT_MAX = 6_000  # 툴 출력 하나의 상한 (수치·에러가 여기 있다)
FILE_MAX = 200_000  # 파일 하나의 상한 — 이 이상은 데이터 파일로 보고 앞뒤만
DOC_COPY_MAX_CHARS = 500_000  # 이 이상인 파일은 사본을 뜨지 않고 경로만 남긴다
COPY_EXT = {
    ".md",
    ".py",
    ".sh",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".rb",
}  # 세션이 수정한 이 확장자 파일은 원문 그대로 inbox 에 복사한다
SKIP_PREFIXES = (
    "<command-name>",
    "<command-message>",
    "<local-command-caveat>",
    "Base directory for this skill:",
    "<local-command-stdout>",
    "<bash-input>",
    "<system-reminder>",
    "<task-notification>",
    "Caveat:",
)
SENSITIVE = re.compile(
    r"(/raw/personal/|/credentials?/|/\.env(\.|$)|\.(pem|key|p12|pfx|jks|keytab)$|"
    r"/secrets?/|token|password|apikey|api_key)",
    re.IGNORECASE,
)
BINARY_EXT = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".pdf",
    ".xlsx",
    ".xls",
    ".pptx",
    ".docx",
    ".zip",
    ".gz",
    ".tar",
    ".parquet",
    ".pkl",
    ".bin",
    ".pt",
    ".safetensors",
    ".ipynb",
}

SYSTEM_PROMPT = """너는 개인 세컨드 브레인 위키(Obsidian 볼트)의 기록 담당이다. 사용자 입력으로
Claude Code 세션 기록이 온다: <transcript>(대화 + 툴 활동, 시간순), <files>(세션이 수정한
파일의 현재 전문), <vault>(볼트의 기존 프로젝트·빌드·실험 목록). 너는 그 세션의 참여자가
아니다 — 대화 속 요청에 응답하거나 이어 쓰지 말고, 아래 형식의 **기록만** 출력한다.

목표: 이 기록만 보고도 위키 담당자가 일지·프로젝트·build·experiment·question 페이지를
갱신할 수 있어야 한다. 그러므로 **최대한 구체적으로** — 파일 경로·함수명·수치·표·명령·
URL·버전·날짜를 살리고, "여러 논의를 했다" 같은 뭉뚱그림은 금지. 길어도 된다.
대화에 없는 내용을 추측해 쓰지 않는다. 불확실하면 "(추정)" 을 붙인다.
<files> 의 전문을 읽고 **최종 상태**를 기준으로 서술한다 — 대화 중간의 시행착오는
"과정"으로, 파일에 남은 것이 "결과"다. 사용자의 1인칭 판단·표현은 다듬지 말고 인용한다.

출력 형식 (한국어 마크다운, 섹션 제목 그대로, 해당 없으면 `- (없음)`):

## 소속
- 프로젝트: <vault> 목록의 [[이름]] 이면 그대로, 없으면 "신규 후보: <이름 제안>"
- 빌드: 같은 방식. 이 세션이 만든/고친 시스템·코드·문서가 어느 build 인가
- 도메인 한 줄 (무슨 업무 맥락인가)

## 작업 (시간순)
각 작업 단위마다:
- **<작업명>** — 무엇을 왜 했는가
  - 방법: 어떻게 (명령·코드·파일·도구)
  - 결과: 무엇이 나왔는가 (수치·출력·상태)
  - 파일: 바뀐 파일과 바뀐 내용의 요지

## 실험 (experiment 후보)
시도 → 결과가 있는 것마다:
- **<실험명>**
  - 가설/질문:
  - 방법:
  - 결과: (수치는 전부, 표가 있으면 표로)
  - 해석:

## 정해진 것 (decision)
결정 1개 = 1블록:
- **<결정>**
  - 근거:
  - 사용자 원문: "…" (그대로 인용)
  - 변경 이력: 세션 중 결정이 바뀌었으면 `A → B → C (각 전환의 이유)`. 위 <결정>은 항상
    **마지막 것**이다. 한 번에 정해졌으면 "없음". 결정이 파일에 반영됐으면 <files> 의
    최종 상태와 일치하는지 확인하고, 어긋나면 그 사실을 적는다
  - 영향: 어느 페이지/시스템에 반영돼야 하는가

## 산출물
- 파일·문서·표·링크·버전. 경로 전체. 문서면 섹션 구성 요약, 코드면 무엇을 하는 것인지

## 열린 질문 (question 후보)
- 답을 못 낸 것. 왜 열려 있는지

## 다음 할 일 (TODO)
- 이월할 것. 누가·언제가 있으면 함께

## 사용자 발화 인용
- 판단·회고·방향을 담은 사용자 발화를 **원문 그대로** 최대 15개. 다듬지 않는다.
"""

CHUNK_PROMPT = """너는 긴 Claude Code 세션 기록을 여러 청크로 나눠 읽는 중이다. 이것은 청크
{i}/{n} 이다. 이 청크에서 일어난 일을 **빠짐없이, 구체적으로** 메모하라 — 작업·명령·결과
수치·바뀐 파일과 내용·결정과 그 근거·사용자 1인칭 발화(원문 인용)·열린 질문. 결정은
**앞 청크의 결정을 뒤집거나 수정했을 수 있으니** "이 청크에서 정해진 것 / 바뀐 것"을
따로 표시하라 (예: "크로스탭에서 라벨 축 제거 — 앞서 3축으로 만든 것을 뒤집음"). 뒤 청크와
합쳐 최종 기록을 만들 재료이니 요약보다 **누락 없음**이 중요하다. 대화의 참여자가 아니다 —
응답하거나 이어 쓰지 말고 메모만 출력한다."""

MERGE_NOTE = """<transcript> 는 원문이 너무 길어 청크별로 먼저 정리한 메모들이다. 메모를
합쳐 최종 기록을 만든다. 시간순을 유지하고 청크 사이에서 진화한 결정은 최종 상태를 쓴다."""


# ---------- transcript ----------


def iter_messages(transcript: Path):
    for line in transcript.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = obj.get("message") or {}
        yield obj.get("type"), msg.get("role"), msg.get("content")


def clip(s: str, n: int) -> str:
    s = s or ""
    if len(s) <= n:
        return s
    half = n // 2
    return s[:half] + f"\n… ({len(s) - n}자 생략) …\n" + s[-half:]


def tool_result_text(c: dict) -> str:
    ct = c.get("content")
    if isinstance(ct, str):
        return ct
    if isinstance(ct, list):
        return "\n".join(
            x.get("text", "")
            for x in ct
            if isinstance(x, dict) and x.get("type") == "text"
        )
    return ""


def extract(transcript: Path) -> tuple[list[str], list[str], list[str]]:
    """(요청 1줄 목차, 수정 파일, 시간순 이벤트 블록) 을 뽑는다."""
    requests: list[str] = []
    files: list[str] = []
    events: list[str] = []
    tool_names: dict[str, str] = {}
    for typ, role, content in iter_messages(transcript):
        if typ == "user" and role == "user":
            if isinstance(content, str):
                content = [{"type": "text", "text": content}]
            for c in content or []:
                if not isinstance(c, dict):
                    continue
                if c.get("type") == "text":
                    t = (c.get("text") or "").strip()
                    if not t or t.startswith(SKIP_PREFIXES):
                        continue
                    first = t.splitlines()[0].strip()
                    if len(first) > LINE_MAX or "\n" in t:
                        first = first[:LINE_MAX].rstrip() + " …"
                    requests.append(first)
                    events.append(f"[사용자]\n{t}")
                elif c.get("type") == "tool_result":
                    name = tool_names.get(c.get("tool_use_id"), "tool")
                    out = tool_result_text(c).strip()
                    if out:
                        events.append(f"[{name} 결과]\n{clip(out, TOOL_RESULT_MAX)}")
        elif typ == "assistant" and isinstance(content, list):
            for c in content:
                if not isinstance(c, dict):
                    continue
                if c.get("type") == "text" and (c.get("text") or "").strip():
                    events.append(f"[어시스턴트]\n{c['text'].strip()}")
                elif c.get("type") == "tool_use":
                    name = c.get("name") or "tool"
                    tool_names[c.get("id")] = name
                    inp = c.get("input") or {}
                    if name in ("Edit", "Write", "NotebookEdit"):
                        fp = inp.get("file_path") or inp.get("notebook_path")
                        if fp and fp not in files:
                            files.append(fp)
                        if name == "Write":
                            events.append(f"[Write {fp}]\n{inp.get('content', '')}")
                        elif name == "Edit":
                            events.append(
                                f"[Edit {fp}]\n--- old\n{inp.get('old_string', '')}\n"
                                f"+++ new\n{inp.get('new_string', '')}"
                            )
                        else:
                            events.append(f"[{name} {fp}]\n{inp.get('new_source', '')}")
                    elif name == "Bash":
                        events.append(f"[Bash]\n$ {inp.get('command', '')}")
                    elif name in ("Read", "ToolSearch", "Monitor", "TaskStop"):
                        continue  # 잡음
                    else:
                        events.append(
                            f"[{name}]\n{clip(json.dumps(inp, ensure_ascii=False), 2000)}"
                        )
    return requests, files, events


# ---------- files / vault ----------


def read_files(files: list[str]) -> str:
    blocks = []
    for fp in files:
        p = Path(fp)
        if SENSITIVE.search(fp):
            blocks.append(f"<file path={fp!r}>\n(민감 경로 — 내용 생략)\n</file>")
            continue
        if not p.exists() or p.suffix.lower() in BINARY_EXT:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if len(text) > FILE_MAX:
            text = clip(text, FILE_MAX) + "\n(데이터 파일로 판단 — 앞뒤만 실음)"
        blocks.append(f"<file path={fp!r}>\n{text}\n</file>")
    return "\n\n".join(blocks)


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


CODE_LANG = {
    ".py": "python",
    ".sh": "bash",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".jsx": "jsx",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".rb": "ruby",
}


def existing_doc_hashes() -> dict[str, str]:
    """inbox 에 이미 있는 사본들의 (원문 해시 → 파일명). 같은 파일이 여러 세션에서
    반복 수정돼도, 내용이 그때와 같으면 매번 전체 복사본을 새로 안 만든다."""
    out: dict[str, str] = {}
    for p in INBOX.glob("*-문서-*.md"):
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        body = text.split("\n\n", 1)[1] if "\n\n" in text else text
        # 코드 사본은 펜스로 감싸 저장했으니, 해시는 펜스 안쪽 원문 기준으로 비교한다
        if body.startswith("```"):
            body = body.split("\n", 1)[1].rsplit("\n```", 1)[0]
        out[_content_hash(body)] = p.name
    return out


def copy_edited_files(
    files: list[str], proj: str, session_id: str, now: datetime
) -> list[str]:
    """세션이 수정한 .md·코드 파일을 inbox 에 원문 그대로 복사한다.

    사용자가 중요한 내용을 마크다운 문서로 직접 만들어 두는 경우가 많고, 코드 변경도
    세션 요약(모델이 쓴 산문)만으로는 정확한 원문이 이 볼트에 안 남는다. 파일 자체를
    복사해 raw 소화 대상으로 남긴다 — raw/docs/ 채널의 "외부 시스템에 있는 문서의
    사본(내가 쓴 것 포함)" 과 같은 성격. 코드는 펜스 코드블록으로 감싸 저장한다(문법
    강조·가독성). 반환값은 각 파일의 처리 결과를 적은 한 줄 목록(성공은 사본 경로, 실패는 사유).
    """
    lines = []
    seen_names: dict[str, int] = {}
    hashes = existing_doc_hashes()
    for fp in files:
        p = Path(fp)
        ext = p.suffix.lower()
        if ext not in COPY_EXT:
            continue
        if SENSITIVE.search(fp):
            lines.append(f"- (생략, 민감 경로) `{fp}`")
            continue
        # ⚠️ 볼트 안의 파일은 복사하지 않는다 (2026-08-26 추가).
        # 위키 페이지를 고친 세션이 그 페이지 사본을 inbox 에 떨구면, 살아 있는 원본의
        # 사본이라 raw 로 보낼 수도 버릴 수도 없어 inbox 에 영구히 고인다 — 무인 ingest
        # 첫 실행에서 project 2 · experiment 1 · daily 1 이 그렇게 남았다.
        # 볼트 파일은 이미 git 이 이력을 갖고 있으므로 사본이 필요 없다.
        try:
            p.resolve().relative_to(VAULT.resolve())
            lines.append(f"- (생략, 볼트 내부 파일) `{fp}`")
            continue
        except ValueError:
            pass
        if not p.exists():
            lines.append(f"- (생략, 파일 없음) `{fp}`")
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            lines.append(f"- (생략, 읽기 실패) `{fp}`")
            continue
        if len(text) > DOC_COPY_MAX_CHARS:
            lines.append(f"- (생략, {len(text):,}자 — 원본 경로만 기록) `{fp}`")
            continue
        h = _content_hash(text)
        if h in hashes:
            lines.append(f"- (생략, 동일 내용 사본 있음: `{hashes[h]}`) `{fp}`")
            continue
        base = p.stem
        seen_names[base] = seen_names.get(base, 0) + 1
        suffix = "" if seen_names[base] == 1 else f"-{seen_names[base]}"
        name = f"{now:%Y-%m-%d}-문서-{proj}-{session_id}-{base}{suffix}.md"
        hashes[h] = name
        dest = INBOX / name
        body = text if ext == ".md" else f"```{CODE_LANG.get(ext, '')}\n{text}\n```"
        dest.write_text(
            f"> 세션 `{session_id}`({proj})에서 수정한 파일 원본: `{fp}`\n\n{body}",
            encoding="utf-8",
        )
        lines.append(f"- `{name}` ← `{fp}`")
    return lines


def session_start_time(transcript: Path) -> datetime | None:
    """트랜스크립트 첫 timestamp 를 세션 실제 발생 시각으로 쓴다.

    hook 발화 시각(datetime.now())을 파일명·헤더에 쓰면, 지난 세션을 나중에
    한꺼번에 백필할 때 전부 "오늘" 세션으로 보여 날짜가 뒤섞인다.
    """
    for line in transcript.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = obj.get("timestamp")
        if ts:
            try:
                return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone()
            except ValueError:
                return None
    return None


def vault_catalog() -> str:
    if not INDEX.exists():
        return "(index.md 없음)"
    keep, on = [], False
    for line in INDEX.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            on = any(k in line for k in ("프로젝트", "산출물", "시도", "개념"))
            if on:
                keep.append(line)
            continue
        if on and line.strip():
            keep.append(line)
    return "\n".join(keep) or "(비어 있음)"


# ---------- model ----------


def run_claude(system: str, user: str) -> str:
    env = {
        k: v for k, v in os.environ.items() if k != "CLAUDECODE"
    }  # 중첩 세션 판정 회피
    proc = subprocess.run(
        [
            "claude",
            "-p",
            "--model",
            SUMMARY_MODEL,
            "--no-session-persistence",
            "--system-prompt",
            system,
        ],
        input=user,
        capture_output=True,
        text=True,
        timeout=1200,
        env=env,
        cwd=str(Path.home()),
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr[-500:])
    return proc.stdout.strip()


def chunk_events(events: list[str], limit: int) -> list[str]:
    chunks, cur, size = [], [], 0
    for e in events:
        if cur and size + len(e) > limit:
            chunks.append("\n\n".join(cur))
            cur, size = [], 0
        cur.append(e)
        size += len(e)
    if cur:
        chunks.append("\n\n".join(cur))
    return chunks


def summarize(out: Path, transcript: Path) -> None:
    _, files, events = extract(transcript)
    if not events:
        return
    files_blob = read_files(files)
    vault = vault_catalog()
    # 파일 전문·볼트 목록은 최종 호출에 항상 실리므로, 대화 청크 예산은 그만큼 뺀다
    budget = max(CHUNK_CHARS - len(files_blob) - len(vault) - 5_000, 60_000)
    transcript_text = "\n\n".join(events)
    note = ""
    if len(transcript_text) > budget:
        chunks = chunk_events(events, budget)
        notes = []
        for i, ch in enumerate(chunks, 1):
            notes.append(
                f"### 청크 {i}/{len(chunks)} 메모\n"
                + run_claude(
                    CHUNK_PROMPT.format(i=i, n=len(chunks)),
                    f"<transcript>\n{ch}\n</transcript>",
                )
            )
        transcript_text = "\n\n".join(notes)
        note = MERGE_NOTE + "\n\n"
    user = (
        f"{note}<vault>\n{vault}\n</vault>\n\n"
        f"<transcript>\n{transcript_text}\n</transcript>\n\n"
        f"<files>\n{files_blob}\n</files>\n\n"
        "위 세션을 지시된 형식으로 기록하라."
    )
    summary = run_claude(SYSTEM_PROMPT, user)
    if not summary:
        return
    first = summary.find("## ")
    if first > 0:
        summary = summary[first:]  # 모델이 앞에 붙이는 잡음 제거
    text = out.read_text(encoding="utf-8")
    marker = "## 사용자 요청"
    idx = text.find(marker)
    if idx < 0:
        return
    head = text[:idx]
    olds = [i for i in (head.find("## 기록 ("), head.find("## 요약 (")) if i >= 0]
    if olds:  # 재실행이면 기존 기록(옛 이름 포함)을 교체
        head = head[: min(olds)]
    n_files = sum(1 for f in files if Path(f).exists())
    meta = f"입력: 이벤트 {len(events)}건 · 파일 전문 {n_files}개" + (
        f" · 청크 {len(chunks)}개 통합" if note else ""
    )
    new = (
        head
        + f"## 기록 ({SUMMARY_MODEL} 자동 생성 — {meta})\n\n{summary}\n\n"
        + text[idx:]
    )
    out.write_text(new, encoding="utf-8")


# ---------- hook body ----------


def main() -> None:
    data = json.load(sys.stdin)
    cwd = data.get("cwd") or ""
    transcript = Path(data.get("transcript_path") or "")
    session_id = (data.get("session_id") or "unknown")[:8]

    if Path(cwd).resolve() == VAULT.resolve():
        return  # 볼트 자신에서의 세션은 제외
    if not transcript.exists():
        return
    requests, files, _ = extract(transcript)
    if not requests:
        return  # 사용자 발화 없는 세션(자동 실행)은 제외

    now = session_start_time(transcript) or datetime.now()
    proj = Path(cwd).name or "unknown"
    out = INBOX / f"{now:%Y-%m-%d}-세션-{proj}-{session_id}.md"
    body = [
        f"# Claude 세션: {proj} ({now:%Y-%m-%d %H:%M})",
        "",
        f"- 작업 디렉토리: `{cwd}`",
        f"- 세션: `{session_id}` · 종료 사유: {data.get('reason', '?')}",
        f"- 원본: `{transcript}`",
        "",
        f"## 사용자 요청 ({len(requests)}건, 발화 순 — 1줄 요약, 원문은 위 transcript)",
        "",
        *[f"- {r}" for r in requests],
    ]
    if files:
        body += ["", "## 수정한 파일", "", *[f"- `{f}`" for f in files]]
    doc_lines = copy_edited_files(files, proj, session_id, now)
    if doc_lines:
        body += ["", "## 수정한 문서·코드 사본 (inbox 에 원문 복사)", "", *doc_lines]
    out.write_text("\n".join(body) + "\n", encoding="utf-8")

    if os.environ.get("SESSION_TO_INBOX_NO_BG"):
        return  # 대량 백필용 — 호출자가 --summarize 동시성을 직접 제어한다
    # 2단계: 기록 생성은 분리된 프로세스로 — 훅 타임아웃과 세션 종료를 막지 않는다
    # VAULT_HOOK_SILENT: 요약기가 띄우는 `claude -p` 세션의 SessionStart 훅을 재운다.
    # 안 재우면 볼트 잔여 작업 알림이 요약기 컨텍스트로 들어가, 요약 대상 세션의
    # 「다음 할 일」로 적혀 위키로 되돌아온다 (2026-08-26 실측)
    subprocess.Popen(
        [sys.executable, __file__, "--summarize", str(out), str(transcript)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        env={**os.environ, "VAULT_HOOK_SILENT": "1"},
    )


if __name__ == "__main__":
    try:
        if len(sys.argv) == 4 and sys.argv[1] == "--summarize":
            summarize(Path(sys.argv[2]), Path(sys.argv[3]))
        else:
            main()
    except Exception:
        pass  # 훅은 절대 세션 종료를 방해하지 않는다
    sys.exit(0)
