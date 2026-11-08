"""구매 번호 자동 채점."""
from . import db

LOTTO_PRIZE = {1: "1등", 2: "2등", 3: "3등", 4: "4등 (5만원)", 5: "5등 (5천원)"}
PENSION_PRIZE = {
    1: "1등 (월 700만원 × 20년)", 2: "2등 (월 100만원 × 10년)", 3: "3등 (100만원)",
    4: "4등 (10만원)", 5: "5등 (5만원)", 6: "6등 (5천원)", 7: "7등 (1천원)",
}


def lotto_rank(nums, win, bonus):
    m = len(set(nums) & set(win))
    if m == 6:
        return 1, m
    if m == 5 and bonus in nums:
        return 2, m
    return {5: 3, 4: 4, 3: 5}.get(m), m


def pension_rank(grp, num, wgrp, wnum, wbonus=None):
    ranks = []
    if num == wnum:
        ranks.append(1 if grp == wgrp else 2)
    else:
        for k, r in ((5, 3), (4, 4), (3, 5), (2, 6), (1, 7)):
            if num[-k:] == wnum[-k:]:
                ranks.append(r)
                break
    bonus_hit = bool(wbonus) and num == wbonus
    tail = 0
    for k in range(6, 0, -1):
        if num[-k:] == wnum[-k:]:
            tail = k
            break
    return (ranks[0] if ranks else None), bonus_hit, tail


def check(purchase):
    """구매 1건 → {'status': 'pending'|'done', 'text': str, 'rank': int|None}"""
    if purchase["game"] == "lotto":
        draw = db.lotto_draw(purchase["round"])
        if not draw:
            return {"status": "pending", "text": "추첨 결과 대기 (당첨번호 미입력)", "rank": None}
        nums = [int(x) for x in purchase["numbers"].split(",")]
        rank, m = lotto_rank(nums, draw[0], draw[1])
        bonus_txt = " + 보너스" if (m == 5 and draw[1] in nums) else ""
        text = f"{m}개 일치{bonus_txt} · " + (LOTTO_PRIZE[rank] if rank else "낙첨")
        return {"status": "done", "text": text, "rank": rank, "hits": sorted(set(nums) & set(draw[0]))}
    draw = db.pension_draw(purchase["round"])
    if not draw:
        return {"status": "pending", "text": "추첨 결과 대기 (당첨번호 미입력)", "rank": None}
    grp, num = purchase["numbers"].split("|")
    rank, bonus_hit, tail = pension_rank(int(grp), num, draw[0], draw[1], draw[2])
    parts = [f"끝 {tail}자리 일치" if tail else "끝자리 불일치"]
    parts.append(PENSION_PRIZE[rank] if rank else "낙첨")
    if bonus_hit:
        parts.append("보너스 당첨 (월 100만원 × 10년)")
    return {"status": "done", "text": " · ".join(parts), "rank": rank or (0 if bonus_hit else None), "tail": tail}
