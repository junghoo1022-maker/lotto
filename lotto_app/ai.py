"""Claude 분석.

방식 B: 이 PC에 설치되어 본인 계정으로 로그인된 Claude Code 를 `claude -p` 로 실행.
        (로그인 토큰을 직접 읽거나 저장하지 않음. 구독 사용 한도에서 차감)
방식 A: Claude Code 가 없으면 질문 내용을 클립보드에 복사 → Claude 앱에 붙여넣기.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TIMEOUT = 240


def find_claude():
    for name in ("claude", "claude.exe", "claude.cmd"):
        p = shutil.which(name)
        if p:
            return p
    home = Path.home()
    candidates = [
        home / ".local" / "bin" / "claude.exe",
        home / ".local" / "bin" / "claude",
        home / "AppData" / "Roaming" / "npm" / "claude.cmd",
        home / ".claude" / "local" / "claude.exe",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return None


def build_prompt(game, stats_text, candidates_text, round_no):
    title = "로또 6/45" if game == "lotto" else "연금복권 720+"
    rule = (
        "로또: 1~45 중 6개, 5세트를 추천하세요."
        if game == "lotto"
        else "연금복권: 1~5조 각각 6자리 번호 5개씩(총 25개), 조마다 서로 다른 번호로 추천하세요. "
             "25장의 끝 1자리가 0~9를 고르게 포함하도록 하세요."
    )
    return f"""당신은 복권 통계 해설가입니다. 아래는 제 PC 프로그램이 계산한 {title} 과거 당첨 통계와 프로그램이 뽑은 후보 번호입니다.
{title} 제 {round_no}회를 위한 번호를 골라 주세요.

규칙: {rule}
- 후보 번호를 그대로 써도 되고, 통계를 보고 바꿔도 됩니다.
- 각 세트(번호)마다 왜 골랐는지 통계 근거를 2~3줄로 구체적으로 설명하세요.
- 마지막에 한 줄로 "추첨은 독립 시행이라 당첨 확률은 어떤 번호든 같다"는 점을 밝혀 주세요.
- 한국어로, 파일을 읽거나 도구를 쓰지 말고 텍스트로만 답하세요.

[통계 요약]
{stats_text}
[프로그램 후보 번호]
{candidates_text}
"""


def ask_claude(prompt):
    """(ok, text) 반환. 실패 시 ok=False 와 원인."""
    exe = find_claude()
    if not exe:
        return False, "이 PC에서 Claude Code(claude)를 찾지 못했습니다."
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    workdir = tempfile.mkdtemp(prefix="lotto_ai_")  # 빈 폴더에서 실행 (내 파일에 접근하지 않도록)
    try:
        proc = subprocess.run(
            [exe, "-p", "--output-format", "text"],
            input=prompt.encode("utf-8"),
            capture_output=True,
            timeout=TIMEOUT,
            cwd=workdir,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            **kwargs,
        )
    except subprocess.TimeoutExpired:
        return False, f"Claude 응답이 {TIMEOUT}초 안에 오지 않았습니다."
    except OSError as e:
        return False, f"Claude Code 실행 실패: {e}"
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    out = proc.stdout.decode("utf-8", errors="replace").strip()
    err = proc.stderr.decode("utf-8", errors="replace").strip()
    if proc.returncode != 0 or not out:
        msg = err or out or f"종료 코드 {proc.returncode}"
        return False, f"Claude Code 실행 오류: {msg[:600]}\n(Claude Code에 로그인되어 있는지 확인하세요: 터미널에서 claude 실행)"
    return True, out
