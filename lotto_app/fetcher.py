"""동행복권 당첨번호 자동 수집 + 직접 입력 텍스트 파싱.

주의: 동행복권 사이트 구조/주소가 바뀌면 자동 수집이 실패할 수 있습니다.
실패하면 data/fetch_log.txt 에 원인이 남고, 프로그램의 '당첨번호 입력'으로 보충하면 됩니다.
"""
import re
import time
from datetime import datetime

import requests

from . import db, paths, rounds

LOTTO_URL = "https://www.dhlottery.co.kr/common.do?method=getLottoNumber&drwNo={rnd}"
PENSION_URL = "https://www.dhlottery.co.kr/gameResult.do?method=win720&Round={rnd}"
TIMEOUT = 8


class FetchError(Exception):
    pass


def log(msg: str):
    try:
        with open(paths.log_path(), "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")
    except OSError:
        pass


def is_online() -> bool:
    try:
        requests.head("https://www.dhlottery.co.kr", timeout=4, allow_redirects=True)
        return True
    except requests.RequestException:
        return False


def _session():
    s = requests.Session()
    s.headers.update({"Accept": "application/json, text/html;q=0.9"})
    return s


def fetch_lotto_round(session, rnd: int):
    try:
        res = session.get(LOTTO_URL.format(rnd=rnd), timeout=TIMEOUT, allow_redirects=False)
    except requests.RequestException as e:
        raise FetchError(f"로또 {rnd}회: 네트워크 오류 ({e.__class__.__name__})")
    if res.status_code in (301, 302, 303, 307, 308):
        raise FetchError(
            f"로또 {rnd}회: 사이트가 다른 페이지로 넘김(HTTP {res.status_code} → {res.headers.get('Location')}). "
            "접속 차단이거나 주소가 바뀐 것일 수 있습니다."
        )
    if res.status_code != 200:
        raise FetchError(f"로또 {rnd}회: HTTP {res.status_code}")
    try:
        data = res.json()
    except ValueError:
        raise FetchError(f"로또 {rnd}회: JSON이 아닌 응답 (앞부분: {res.text[:120]!r})")
    if data.get("returnValue") != "success":
        return None  # 아직 추첨 전
    nums = [data[f"drwtNo{i}"] for i in range(1, 7)]
    return nums, data["bnusNo"], data.get("drwNoDate")


_TAG = re.compile(r"<[^>]+>")


def _parse_pension_html(html: str, rnd: int):
    text = re.sub(r"\s+", " ", _TAG.sub(" ", html))
    if f"{rnd}회" not in text:
        raise FetchError(f"연금 {rnd}회: 결과 페이지에서 회차 표시를 찾지 못함")
    m = re.search(r"([1-5])\s*조\s*((?:\d\s*){6})", text)
    if not m:
        raise FetchError(f"연금 {rnd}회: 1등 번호 형식을 찾지 못함 (페이지 구조 변경 가능)")
    grp = int(m.group(1))
    num = re.sub(r"\D", "", m.group(2))
    bonus = None
    b = re.search(r"보너스.{0,80}?각\s*조\s*((?:\d\s*){6})", text)
    if b:
        bonus = re.sub(r"\D", "", b.group(1))
    return grp, num, bonus


def fetch_pension_round(session, rnd: int):
    try:
        res = session.get(PENSION_URL.format(rnd=rnd), timeout=TIMEOUT, allow_redirects=False)
    except requests.RequestException as e:
        raise FetchError(f"연금 {rnd}회: 네트워크 오류 ({e.__class__.__name__})")
    if res.status_code in (301, 302, 303, 307, 308):
        raise FetchError(f"연금 {rnd}회: 다른 페이지로 넘김(HTTP {res.status_code}). 차단 또는 주소 변경 가능")
    if res.status_code != 200:
        raise FetchError(f"연금 {rnd}회: HTTP {res.status_code}")
    res.encoding = res.apparent_encoding or "utf-8"
    return _parse_pension_html(res.text, rnd)


def update_all(progress=None, stop_after_errors=3):
    """빠진 회차를 모두 수집. progress(msg, ratio) 콜백. 결과 요약 dict 반환."""
    def report(msg, ratio=None):
        if progress:
            progress(msg, ratio)

    summary = {"lotto_added": 0, "pension_added": 0, "errors": []}
    session = _session()

    # 로또
    have = db.lotto_rounds_set()
    latest = rounds.lotto_latest_drawn()
    missing = [r for r in range(1, latest + 1) if r not in have]
    errors = 0
    for i, rnd in enumerate(missing):
        report(f"로또 {rnd}회 수집 중… ({i + 1}/{len(missing)})", (i + 1) / max(len(missing), 1) * 0.6)
        try:
            got = fetch_lotto_round(session, rnd)
        except FetchError as e:
            summary["errors"].append(str(e)); log(str(e)); errors += 1
            if errors >= stop_after_errors:
                summary["errors"].append("로또: 연속 오류로 자동 수집을 중단했습니다.")
                break
            continue
        if got is None:
            break
        nums, bonus, d = got
        db.upsert_lotto(rnd, d or str(rounds.lotto_draw_date(rnd)), nums, bonus, source="auto")
        summary["lotto_added"] += 1
        errors = 0
        time.sleep(0.05)

    # 연금
    have = db.pension_rounds_set()
    latest = rounds.pension_latest_drawn()
    missing = [r for r in range(1, latest + 1) if r not in have]
    errors = 0
    for i, rnd in enumerate(missing):
        report(f"연금복권 {rnd}회 수집 중… ({i + 1}/{len(missing)})", 0.6 + (i + 1) / max(len(missing), 1) * 0.4)
        try:
            grp, num, bonus = fetch_pension_round(session, rnd)
        except FetchError as e:
            summary["errors"].append(str(e)); log(str(e)); errors += 1
            if errors >= stop_after_errors:
                summary["errors"].append("연금복권: 연속 오류로 자동 수집을 중단했습니다.")
                break
            continue
        db.upsert_pension(rnd, str(rounds.pension_draw_date(rnd)), grp, num, bonus, source="auto")
        summary["pension_added"] += 1
        errors = 0
        time.sleep(0.05)

    log(f"수집 완료: 로또 +{summary['lotto_added']}, 연금 +{summary['pension_added']}, 오류 {len(summary['errors'])}건")
    report("수집 완료", 1.0)
    return summary


def diagnose():
    """수집 테스트: 각 1회씩 시도하고 결과를 사람이 읽을 문장으로 반환."""
    s = _session()
    lines = []
    try:
        r = rounds.lotto_latest_drawn()
        got = fetch_lotto_round(s, r)
        lines.append(f"✅ 로또 {r}회 수집 성공: {got[0]} + 보너스 {got[1]}" if got else f"⚠️ 로또 {r}회 아직 결과 없음")
    except FetchError as e:
        lines.append(f"❌ {e}")
    try:
        r = rounds.pension_latest_drawn()
        grp, num, bonus = fetch_pension_round(s, r)
        lines.append(f"✅ 연금 {r}회 수집 성공: {grp}조 {num} (보너스 {bonus or '미확인'})")
    except FetchError as e:
        lines.append(f"❌ {e}")
    for ln in lines:
        log("[수집 테스트] " + ln)
    return "\n".join(lines)


# ---------- 직접 입력 텍스트 파싱 ----------
def parse_lotto_lines(text: str):
    """한 줄에 '회차 n1 n2 n3 n4 n5 n6 보너스' (구분자 자유). [(rnd, nums, bonus)]"""
    out, bad = [], []
    for ln in text.splitlines():
        nums = [int(x) for x in re.findall(r"\d+", ln)]
        if not nums:
            continue
        if len(nums) != 8:
            bad.append(ln.strip()); continue
        rnd, six, bonus = nums[0], nums[1:7], nums[7]
        try:
            db.validate_lotto(sorted(six), bonus)
        except ValueError:
            bad.append(ln.strip()); continue
        out.append((rnd, sorted(six), bonus))
    return out, bad


def parse_pension_lines(text: str):
    """한 줄에 '회차 조 6자리 [보너스6자리]'. 예: 319 2 841093 123456"""
    out, bad = [], []
    for ln in text.splitlines():
        toks = re.findall(r"\d+", ln)
        if not toks:
            continue
        if len(toks) == 9 or len(toks) == 8:  # '회차 조 1 2 3 4 5 6' 처럼 띄어 쓴 경우
            toks = [toks[0], toks[1], "".join(toks[2:8])] + ([] if len(toks) == 8 else [toks[8]])
        if len(toks) not in (3, 4):
            bad.append(ln.strip()); continue
        rnd, grp, num = int(toks[0]), int(toks[1]), toks[2]
        bonus = toks[3] if len(toks) == 4 else None
        try:
            db.validate_pension(grp, num, bonus)
        except ValueError:
            bad.append(ln.strip()); continue
        out.append((rnd, grp, num, bonus))
    return out, bad
