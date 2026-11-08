"""동행복권 당첨번호 자동 수집 + 직접 입력 텍스트 파싱.

주의: 동행복권 사이트 구조/주소가 바뀌면 자동 수집이 실패할 수 있습니다.
실패하면 data/fetch_log.txt 에 원인이 남고, 프로그램의 '당첨번호 입력'으로 보충하면 됩니다.
"""
import re
import time
from datetime import datetime

import requests

from . import db, paths, rounds

# 2025~2026 사이트 개편 이후 주소 (공개 라이브러리 seongilp/dhlottery-api 에서 사용 중인 것을 참고)
LOTTO_NEW_URL = "https://www.dhlottery.co.kr/lt645/selectPstLt645Info.do"
# 개편 전 주소 (예비)
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
    s.headers.update({
        "User-Agent": "LottoAnalyzer/1.1 (personal use)",
        "Accept-Language": "ko-KR,ko;q=0.9",
    })
    try:  # 첫 방문 쿠키 받기
        s.get("https://www.dhlottery.co.kr/", timeout=TIMEOUT)
    except requests.RequestException:
        pass
    return s


def _snippet(res):
    return f"HTTP {res.status_code}, {res.headers.get('Content-Type', '')}, 앞부분: {res.text[:200]!r}"


def fetch_lotto_new(session, rnd: int):
    """새 주소. 응답 목록에 여러 회차가 올 수 있어 {round: (nums, bonus, date)} 로 반환."""
    try:
        res = session.get(LOTTO_NEW_URL, params={"srchLtEpsd": rnd}, timeout=TIMEOUT, allow_redirects=False,
                          headers={"Accept": "application/json, text/javascript, */*; q=0.01",
                                   "X-Requested-With": "XMLHttpRequest",
                                   "Referer": "https://www.dhlottery.co.kr/"})
    except requests.RequestException as e:
        raise FetchError(f"로또 {rnd}회(새 주소): 네트워크 오류 ({e.__class__.__name__})")
    if res.status_code != 200:
        raise FetchError(f"로또 {rnd}회(새 주소): {_snippet(res)}")
    try:
        items = (res.json().get("data") or {}).get("list") or []
    except ValueError:
        raise FetchError(f"로또 {rnd}회(새 주소): JSON 아님 · {_snippet(res)}")
    out = {}
    if not items:
        return out  # 정상 응답인데 목록이 비어 있음 = 아직 추첨 전
    for it in items:
        try:
            r = int(it["ltEpsd"])
            nums = [int(it[f"tm{n}WnNo"]) for n in range(1, 7)]
            bonus = int(it["bnsWnNo"])
        except (KeyError, TypeError, ValueError):
            continue
        out[r] = (nums, bonus, None)
    if not out:
        fetcher_keys = list(items[0].keys())[:15] if items else []
        raise FetchError(f"로또 {rnd}회(새 주소): 번호 항목을 찾지 못함 · 키 {fetcher_keys} · {_snippet(res)}")
    return out


def fetch_lotto_any(session, rnd: int):
    """새 주소 → 예전 주소 순서로 시도. {round: (nums, bonus, date)} 또는 {} (아직 추첨 전)."""
    errors = []
    try:
        return fetch_lotto_new(session, rnd)  # 해당 회차가 없으면 아직 추첨 전
    except FetchError as e:
        errors.append(str(e))
    try:
        old = fetch_lotto_round(session, rnd)
        return {rnd: old} if old else {}
    except FetchError as e:
        errors.append(str(e))
    raise FetchError(" / ".join(errors))


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
    """예전 주소 (개편 후 메인으로 넘어감)."""
    try:
        res = session.get(PENSION_URL.format(rnd=rnd), timeout=TIMEOUT, allow_redirects=False)
    except requests.RequestException as e:
        raise FetchError(f"연금 {rnd}회: 네트워크 오류 ({e.__class__.__name__})")
    if res.status_code in (301, 302, 303, 307, 308):
        raise FetchError(f"연금 {rnd}회(예전 주소): 다른 페이지로 넘김(HTTP {res.status_code})")
    if res.status_code != 200:
        raise FetchError(f"연금 {rnd}회(예전 주소): HTTP {res.status_code}")
    res.encoding = res.apparent_encoding or "utf-8"
    return _parse_pension_html(res.text, rnd)


# ---------- 연금복권: 개편된 사이트 ----------
# 개편 후 결과 페이지는 /pt720/result. 이 페이지가 내부에서 부르는 데이터 주소는 아직 확인되지 않아,
# 로또 주소(/lt645/selectPstLt645Info.do, srchLtEpsd) 규칙을 본뜬 후보 + 페이지에서 찾아낸 주소를 차례로 시도합니다.
PENSION_PAGES = ["https://www.dhlottery.co.kr/pt720/result", "https://m.dhlottery.co.kr/pt720/result"]
PENSION_GUESS_URLS = ["https://www.dhlottery.co.kr/pt720/selectPstPt720Info.do"]
PENSION_GUESS_PARAMS = ["srchPsltEpsd", "srchLtEpsd", "srchEpsd", "psltEpsd", "ltEpsd"]
_XHR = {"Accept": "application/json, text/javascript, */*; q=0.01", "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://www.dhlottery.co.kr/pt720/result"}


def discover_pension(session):
    """결과 페이지와 그 스크립트에서 /pt720/...do 주소와 회차 파라미터 이름을 찾아낸다."""
    urls, params, notes = [], [], []
    for page in PENSION_PAGES:
        try:
            res = session.get(page, timeout=TIMEOUT)
        except requests.RequestException as e:
            notes.append(f"{page}: {e.__class__.__name__}")
            continue
        notes.append(f"{page}: HTTP {res.status_code}, 길이 {len(res.text)}")
        texts = [res.text]
        base = page.split("/pt720")[0]
        for src in re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', res.text)[:15]:
            if src.startswith("//") or ("http" in src and "dhlottery" not in src):
                continue
            full = src if src.startswith("http") else base + ("" if src.startswith("/") else "/") + src
            if "pt720" in full or "result" in full or "common" in full or "app" in full:
                try:
                    texts.append(session.get(full, timeout=TIMEOUT).text)
                except requests.RequestException:
                    pass
        for t in texts:
            for u in re.findall(r'["\'](/pt720/[A-Za-z0-9_/]+\.do)', t):
                full = base + u
                if full not in urls:
                    urls.append(full)
            for prm in re.findall(r'\b(srch\w*Epsd\w*|\w*[Ee]psd)\b', t):
                if prm not in params and len(prm) < 30:
                    params.append(prm)
        # 결과 페이지가 번호를 HTML에 직접 넣어 주는 경우를 대비해 원문도 보관
        session._pension_page_html = getattr(session, "_pension_page_html", "") or res.text
    return urls, params, notes


def _find_pension_items(obj):
    """JSON 어디에 있든 '회차'처럼 보이는 키를 가진 dict 들을 찾는다."""
    found = []
    if isinstance(obj, dict):
        if any(re.search(r"epsd|round|drw", k, re.I) for k in obj):
            found.append(obj)
        for v in obj.values():
            found += _find_pension_items(v)
    elif isinstance(obj, list):
        for v in obj:
            found += _find_pension_items(v)
    return found


def _item_to_pension(it):
    """dict 하나 → (round, grp, num, bonus) 추정. 실패 시 None."""
    rnd = grp = num = bonus = None
    digits = {}
    for k, v in it.items():
        kl = k.lower()
        sv = str(v).strip() if v is not None else ""
        if rnd is None and re.search(r"epsd|round|drwno", kl) and sv.isdigit() and "view" not in kl:
            rnd = int(sv)
        elif grp is None and re.search(r"jo|grp|group|bnd|cls", kl) and sv.isdigit() and 1 <= int(sv) <= 5 and "bns" not in kl:
            grp = int(sv)
        elif re.search(r"bns|bonus", kl) and len(sv) == 6 and sv.isdigit():
            bonus = sv
        elif len(sv) == 6 and sv.isdigit() and num is None and "ymd" not in kl and "dt" not in kl:
            num = sv
        m = re.search(r"(\d)$", k)
        if m and sv.isdigit() and len(sv) == 1 and not re.search(r"bns|bonus", kl):
            digits[int(m.group(1))] = sv
    if num is None and all(i in digits for i in range(1, 7)):
        num = "".join(digits[i] for i in range(1, 7))
    if rnd and grp and num:
        return rnd, grp, num, bonus
    return None


def _try_pension_endpoint(session, url, param, rnd):
    res = session.get(url, params={param: rnd}, timeout=TIMEOUT, allow_redirects=False, headers=_XHR)
    if res.status_code != 200:
        raise FetchError(f"{url}?{param}=: {_snippet(res)}")
    try:
        data = res.json()
    except ValueError:
        raise FetchError(f"{url}?{param}=: JSON 아님 · {_snippet(res)}")
    out = {}
    for it in _find_pension_items(data):
        got = _item_to_pension(it)
        if got:
            out[got[0]] = got[1:]
    if not out:
        raise FetchError(f"{url}?{param}=: 번호를 해석하지 못함 · 응답 {str(data)[:400]}")
    return out


def fetch_pension_any(session, rnd: int):
    """{round: (grp, num, bonus)} 반환. 성공한 주소는 기억해 두고 다음부터 먼저 사용."""
    saved = db.get_setting("pension_endpoint")
    tries = []
    if saved and "|" in saved:
        tries.append(tuple(saved.split("|", 1)))
    if not getattr(session, "_pension_discovered", False):
        urls, params, notes = discover_pension(session)
        session._pension_discovered = True
        session._pension_tries = [(u, p) for u in urls + PENSION_GUESS_URLS for p in params + PENSION_GUESS_PARAMS]
        log("[연금 주소 탐색] " + " / ".join(notes) + f" · 찾은 주소 {urls} · 파라미터 후보 {params}")
    for t in getattr(session, "_pension_tries", []):
        if t not in tries:
            tries.append(t)
    errors = []
    for url, param in tries[:40]:
        try:
            out = _try_pension_endpoint(session, url, param, rnd)
            db.set_setting("pension_endpoint", f"{url}|{param}")
            return out
        except (FetchError, requests.RequestException) as e:
            errors.append(str(e)[:300])
    # 최신 회차라면 결과 페이지 HTML에서 직접 읽기
    html = getattr(session, "_pension_page_html", "")
    if html:
        try:
            grp, num, bonus = _parse_pension_html(html, rnd)
            return {rnd: (grp, num, bonus)}
        except FetchError as e:
            errors.append(f"결과 페이지 직접 읽기: {e}")
    try:
        return {rnd: fetch_pension_round(session, rnd)}
    except FetchError as e:
        errors.append(str(e))
    for e in errors:
        log(f"[연금 {rnd}회 시도 실패] {e}")
    raise FetchError(f"연금 {rnd}회: 자동 수집 실패 (시도 {len(errors)}가지, 자세한 내용은 기록 파일)")


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
    cache = {}
    for i, rnd in enumerate(missing):
        report(f"로또 {rnd}회 수집 중… ({i + 1}/{len(missing)})", (i + 1) / max(len(missing), 1) * 0.6)
        if rnd not in cache:
            try:
                cache.update(fetch_lotto_any(session, rnd))
            except FetchError as e:
                summary["errors"].append(str(e)); log(str(e)); errors += 1
                if errors >= stop_after_errors:
                    summary["errors"].append("로또: 연속 오류로 자동 수집을 중단했습니다.")
                    break
                continue
        if rnd not in cache:
            break  # 아직 추첨 전
        nums, bonus, d = cache.pop(rnd)
        db.upsert_lotto(rnd, d or str(rounds.lotto_draw_date(rnd)), nums, bonus, source="auto")
        summary["lotto_added"] += 1
        errors = 0
        time.sleep(0.05)
    for r, (nums, bonus, d) in cache.items():  # 한 번에 같이 받은 다른 회차도 저장
        if r not in db.lotto_rounds_set():
            db.upsert_lotto(r, d or str(rounds.lotto_draw_date(r)), nums, bonus, source="auto")
            summary["lotto_added"] += 1

    # 연금
    have = db.pension_rounds_set()
    latest = rounds.pension_latest_drawn()
    # 최신 회차부터 (공식 사이트는 최근 약 1년치만 조회된다는 안내가 있음)
    missing = [r for r in range(latest, 0, -1) if r not in have]
    errors = 0
    cache = {}
    for i, rnd in enumerate(missing):
        report(f"연금복권 {rnd}회 수집 중… ({i + 1}/{len(missing)})", 0.6 + (i + 1) / max(len(missing), 1) * 0.4)
        if rnd not in cache:
            try:
                cache.update(fetch_pension_any(session, rnd))
            except FetchError as e:
                summary["errors"].append(str(e)); log(str(e)); errors += 1
                if errors >= stop_after_errors:
                    summary["errors"].append("연금복권: 연속 오류로 자동 수집을 중단했습니다.")
                    break
                continue
        if rnd not in cache:
            errors += 1
            continue
        grp, num, bonus = cache.pop(rnd)
        db.upsert_pension(rnd, str(rounds.pension_draw_date(rnd)), grp, num, bonus, source="auto")
        summary["pension_added"] += 1
        errors = 0
        time.sleep(0.05)
    have = db.pension_rounds_set()
    for r, (grp, num, bonus) in cache.items():
        if r not in have and 1 <= r <= latest:
            db.upsert_pension(r, str(rounds.pension_draw_date(r)), grp, num, bonus, source="auto")
            summary["pension_added"] += 1

    log(f"수집 완료: 로또 +{summary['lotto_added']}, 연금 +{summary['pension_added']}, 오류 {len(summary['errors'])}건")
    report("수집 완료", 1.0)
    return summary


def diagnose():
    """수집 테스트: 각 1회씩 시도하고 결과를 사람이 읽을 문장으로 반환."""
    s = _session()
    lines = []
    r = rounds.lotto_latest_drawn()
    try:
        got = fetch_lotto_new(s, r)
        lines.append(f"✅ 로또 {r}회 (새 주소) 성공: {got[r][0]} + 보너스 {got[r][1]}" if r in got
                     else f"⚠️ 로또 새 주소 응답은 왔지만 {r}회가 없음 (받은 회차 {sorted(got)[:5]})")
    except FetchError as e:
        lines.append(f"❌ {e}")
    try:
        got = fetch_lotto_round(s, r)
        lines.append(f"✅ 로또 {r}회 (예전 주소) 성공: {got[0]}" if got else f"⚠️ 로또 {r}회 (예전 주소) 결과 없음")
    except FetchError as e:
        lines.append(f"❌ (예전 주소) {e}")
    r = rounds.pension_latest_drawn()
    try:
        got = fetch_pension_any(s, r)
        if r in got:
            g, num, bonus = got[r]
            lines.append(f"✅ 연금 {r}회 성공: {g}조 {num} (보너스 {bonus or '미확인'}) · 사용 주소 {db.get_setting('pension_endpoint') or '결과 페이지'}")
        else:
            lines.append(f"⚠️ 연금 응답은 왔지만 {r}회가 없음 (받은 회차 {sorted(got)[:5]})")
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
