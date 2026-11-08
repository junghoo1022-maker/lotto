"""SQLite 저장소: 당첨번호, 구매(확정) 내역."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from . import paths

SCHEMA = """
CREATE TABLE IF NOT EXISTS lotto_draws (
    round INTEGER PRIMARY KEY,
    draw_date TEXT,
    n1 INTEGER, n2 INTEGER, n3 INTEGER, n4 INTEGER, n5 INTEGER, n6 INTEGER,
    bonus INTEGER,
    source TEXT
);
CREATE TABLE IF NOT EXISTS pension_draws (
    round INTEGER PRIMARY KEY,
    draw_date TEXT,
    grp INTEGER,
    num TEXT,          -- 6자리 문자열
    bonus TEXT,        -- 보너스 6자리 (없으면 NULL)
    source TEXT
);
CREATE TABLE IF NOT EXISTS purchases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game TEXT NOT NULL,       -- 'lotto' | 'pension'
    round INTEGER NOT NULL,
    numbers TEXT NOT NULL,    -- lotto: "1,2,3,4,5,6" / pension: "3|123456"
    strategy TEXT,
    reasons TEXT,             -- JSON
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


@contextmanager
def connect():
    conn = sqlite3.connect(paths.db_path())
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


# ---------- 로또 ----------
def upsert_lotto(rnd, draw_date, nums, bonus, source="manual"):
    nums = sorted(int(n) for n in nums)
    validate_lotto(nums, bonus)
    with connect() as c:
        c.execute(
            "INSERT OR REPLACE INTO lotto_draws VALUES (?,?,?,?,?,?,?,?,?,?)",
            (int(rnd), draw_date, *nums, int(bonus), source),
        )


def validate_lotto(nums, bonus):
    if len(nums) != 6 or len(set(nums)) != 6:
        raise ValueError("로또 번호는 서로 다른 6개여야 합니다.")
    if any(not 1 <= n <= 45 for n in nums):
        raise ValueError("로또 번호는 1~45 사이여야 합니다.")
    if bonus is not None:
        if not 1 <= int(bonus) <= 45 or int(bonus) in nums:
            raise ValueError("보너스 번호는 1~45이고 당첨번호와 달라야 합니다.")


def lotto_draws():
    """회차 오름차순 [(round, [6개], bonus, date)]"""
    with connect() as c:
        rows = c.execute("SELECT * FROM lotto_draws ORDER BY round").fetchall()
    return [
        (r["round"], [r["n1"], r["n2"], r["n3"], r["n4"], r["n5"], r["n6"]], r["bonus"], r["draw_date"])
        for r in rows
    ]


def lotto_rounds_set():
    with connect() as c:
        return {r[0] for r in c.execute("SELECT round FROM lotto_draws")}


def lotto_draw(rnd):
    with connect() as c:
        r = c.execute("SELECT * FROM lotto_draws WHERE round=?", (rnd,)).fetchone()
    if not r:
        return None
    return [r["n1"], r["n2"], r["n3"], r["n4"], r["n5"], r["n6"]], r["bonus"]


# ---------- 연금 ----------
def validate_pension(grp, num, bonus=None):
    if not 1 <= int(grp) <= 5:
        raise ValueError("조는 1~5 사이여야 합니다.")
    if len(num) != 6 or not num.isdigit():
        raise ValueError("연금복권 번호는 숫자 6자리여야 합니다.")
    if bonus and (len(bonus) != 6 or not bonus.isdigit()):
        raise ValueError("보너스 번호는 숫자 6자리여야 합니다.")


def upsert_pension(rnd, draw_date, grp, num, bonus=None, source="manual"):
    num = str(num).strip()
    bonus = str(bonus).strip() if bonus else None
    validate_pension(grp, num, bonus)
    with connect() as c:
        c.execute(
            "INSERT OR REPLACE INTO pension_draws VALUES (?,?,?,?,?,?)",
            (int(rnd), draw_date, int(grp), num, bonus, source),
        )


def pension_draws():
    with connect() as c:
        rows = c.execute("SELECT * FROM pension_draws ORDER BY round").fetchall()
    return [(r["round"], r["grp"], r["num"], r["bonus"], r["draw_date"]) for r in rows]


def pension_rounds_set():
    with connect() as c:
        return {r[0] for r in c.execute("SELECT round FROM pension_draws")}


def pension_draw(rnd):
    with connect() as c:
        r = c.execute("SELECT * FROM pension_draws WHERE round=?", (rnd,)).fetchone()
    if not r:
        return None
    return r["grp"], r["num"], r["bonus"]


# ---------- 구매 내역 ----------
def add_purchase(game, rnd, numbers, strategy="", reasons=None):
    with connect() as c:
        dup = c.execute(
            "SELECT 1 FROM purchases WHERE game=? AND round=? AND numbers=?",
            (game, rnd, numbers),
        ).fetchone()
        if dup:
            return False
        c.execute(
            "INSERT INTO purchases (game, round, numbers, strategy, reasons, created_at) VALUES (?,?,?,?,?,?)",
            (game, int(rnd), numbers, strategy, json.dumps(reasons or [], ensure_ascii=False),
             datetime.now().strftime("%Y-%m-%d %H:%M")),
        )
        return True


def purchases():
    with connect() as c:
        return [dict(r) for r in c.execute("SELECT * FROM purchases ORDER BY round DESC, game, id").fetchall()]


def delete_purchase(pid):
    with connect() as c:
        c.execute("DELETE FROM purchases WHERE id=?", (pid,))


# ---------- 설정 ----------
def get_setting(key, default=None):
    with connect() as c:
        r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return r[0] if r else default


def set_setting(key, value):
    with connect() as c:
        c.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, str(value)))
