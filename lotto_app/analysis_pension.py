"""연금복권 720+ 자리별 분석 + 조(1~5)마다 서로 다른 번호 5개 생성.

등수 (조 / 6자리 기준):
 1등 조+6자리 일치, 2등 6자리 일치(조 무관), 3등 끝 5자리, 4등 끝 4자리,
 5등 끝 3자리, 6등 끝 2자리, 7등 끝 1자리, 보너스: 보너스 6자리 일치(조 무관)
"""
import random
from collections import Counter
from dataclasses import dataclass

RECENT = 20
PER_GROUP = 5


@dataclass
class PensionStats:
    n_draws: int
    latest_round: int | None
    last_draw: tuple | None          # (grp, num)
    freq: list                       # [pos] -> {digit: count}
    recent: list
    gap: list
    group_freq: dict

    def expected_recent(self):
        return min(RECENT, self.n_draws) / 10


def build_stats(draws):
    """draws: [(round, grp, num, bonus, date)] 오름차순"""
    freq = [Counter() for _ in range(6)]
    recent = [Counter() for _ in range(6)]
    last_seen = [dict() for _ in range(6)]
    for idx, (_r, _g, num, _b, _d) in enumerate(draws):
        for p, ch in enumerate(num):
            freq[p][int(ch)] += 1
            last_seen[p][int(ch)] = idx
    for _r, _g, num, _b, _d in draws[-RECENT:]:
        for p, ch in enumerate(num):
            recent[p][int(ch)] += 1
    total = len(draws)
    gap = [{d: (total - 1 - last_seen[p][d]) if d in last_seen[p] else total for d in range(10)} for p in range(6)]
    return PensionStats(
        n_draws=total,
        latest_round=draws[-1][0] if draws else None,
        last_draw=(draws[-1][1], draws[-1][2]) if draws else None,
        freq=[{d: freq[p][d] for d in range(10)} for p in range(6)],
        recent=[{d: recent[p][d] for d in range(10)} for p in range(6)],
        gap=gap,
        group_freq=dict(Counter(d[1] for d in draws)),
    )


def _weights(stats, p, kind):
    if kind == "hot":
        return {d: (stats.recent[p][d] + 0.5) ** 1.5 for d in range(10)}
    if kind == "cold":
        return {d: (stats.gap[p][d] + 1) ** 0.9 for d in range(10)}
    return {d: 1.0 for d in range(10)}


def _plan(strategy, rng):
    if strategy == "hot":
        return ["hot"] * 4 + ["uniform"]
    if strategy == "cold":
        return ["cold"] * 4 + ["uniform"]
    if strategy == "random":
        return ["uniform"] * 5
    plan = ["hot", "hot", "cold", "cold", "uniform"]
    rng.shuffle(plan)
    return plan


def _ok(num, strategy):
    c = Counter(num)
    if max(c.values()) >= 3:
        return False
    if num in ("123456", "234567", "345678", "456789", "987654", "876543", "765432", "654321"):
        return False
    if strategy != "random":
        odd = sum(int(ch) % 2 for ch in num)
        if not 1 <= odd <= 5:
            return False
    return True


def _last_digit_plan(rng):
    """25장 전체에서 끝자리 0~9가 최소 2번씩 나오도록, 같은 조 안에서는 끝자리가 겹치지 않게."""
    for _ in range(1000):
        pool = list(range(10)) * 2 + rng.sample(range(10), 5)
        rng.shuffle(pool)
        groups = [pool[i * PER_GROUP:(i + 1) * PER_GROUP] for i in range(5)]
        if all(len(set(g)) == PER_GROUP for g in groups):
            return groups
    return [rng.sample(range(10), PER_GROUP) for _ in range(5)]


def generate(stats, strategy="balanced", seed=None):
    """{grp: [ticket,...]} ticket = {grp, num, reasons, strategy}"""
    rng = random.Random(seed)
    last_digits = _last_digit_plan(rng)
    used_nums, used_tail2 = set(), set()
    result = {}
    for gi, grp in enumerate(range(1, 6)):
        tickets = []
        for k in range(PER_GROUP):
            last = last_digits[gi][k]
            for _ in range(5000):
                plan = _plan(strategy, rng)
                digits = [rng.choices(range(10), weights=list(_weights(stats, p, plan[p]).values()))[0] for p in range(5)]
                num = "".join(map(str, digits)) + str(last)
                if num in used_nums or num[-2:] in used_tail2 or not _ok(num, strategy):
                    continue
                break
            used_nums.add(num)
            used_tail2.add(num[-2:])
            tickets.append({
                "grp": grp,
                "num": num,
                "reasons": ticket_reasons(num, plan, stats),
                "strategy": strategy,
            })
        result[grp] = tickets
    return result


def ticket_reasons(num, plan, stats):  # plan: 가중치 추첨 방식(근거 문장은 실제 통계로 판정)
    names = ["1번째", "2번째", "3번째", "4번째", "5번째", "6번째(끝자리)"]
    out = []
    for p, ch in enumerate(num):
        d = int(ch)
        if stats.n_draws == 0:
            out.append(f"{names[p]} {d}: 데이터 없음 · 규칙 필터만 적용")
            continue
        if p == 5:
            head = "[분산] 끝자리 분산 배치 (25장 전체에 0~9 끝자리를 고르게 배정)"
        elif stats.recent[p][d] >= stats.expected_recent() + 1:
            head = f"[핫] 이 자리 최근 {min(RECENT, stats.n_draws)}회 중 {stats.recent[p][d]}회 출현 (평균 {stats.expected_recent():.1f}회)"
        elif stats.gap[p][d] >= 15:
            head = f"[콜드] 이 자리에서 {stats.gap[p][d]}회 연속 미출현 (평균 간격 10회)"
        else:
            head = f"[균형] 평균 수준 숫자 · 균형 보충 (최근 {stats.recent[p][d]}회 출현)"
        out.append(f"{names[p]} {d}: {head} · 역대 이 자리 {stats.freq[p][d]}회")
    out.append("조합 검사: 같은 숫자 3개 이상 X · 일렬 숫자(123456 등) X · 25장 끝 2자리 모두 다름")
    return out


def stats_summary_text(stats):
    if stats.n_draws == 0:
        return "연금복권 당첨번호 데이터 없음."
    lines = [f"수집된 연금복권 회차: {stats.n_draws}개 (최신 {stats.latest_round}회 1등 {stats.last_draw[0]}조 {stats.last_draw[1]})"]
    for p in range(6):
        hot = sorted(range(10), key=lambda d: -stats.recent[p][d])[:3]
        cold = sorted(range(10), key=lambda d: -stats.gap[p][d])[:3]
        lines.append(f"{p + 1}번째 자리 - 최근 많이 나온 숫자 {hot}, 오래 안 나온 숫자 {[(d, stats.gap[p][d]) for d in cold]}")
    return "\n".join(lines) + "\n"
