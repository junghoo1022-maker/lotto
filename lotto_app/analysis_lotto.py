"""로또 6/45 통계 분석 + 근거가 붙는 번호 생성.

추첨은 매 회 독립 시행이므로 어떤 분석도 당첨 확률을 높이지 못합니다.
여기서의 '근거'는 '과거 데이터와 이렇게 맞는다'는 설명입니다.
"""
import random
from collections import Counter
from dataclasses import dataclass, field

RECENT = 20
STRATEGIES = {
    "balanced": "균형형",
    "hot": "핫넘버형",
    "cold": "콜드넘버형",
    "random": "완전랜덤",
}


def ac_value(nums):
    diffs = {abs(a - b) for i, a in enumerate(nums) for b in nums[i + 1:]}
    return len(diffs) - 5


def has_run(nums, length=3):
    s = sorted(nums)
    run = 1
    for a, b in zip(s, s[1:]):
        run = run + 1 if b == a + 1 else 1
        if run >= length:
            return True
    return False


def decade(n):
    return 0 if n < 10 else n // 10


@dataclass
class LottoStats:
    n_draws: int
    latest_round: int | None
    last_draw: list
    freq: dict
    recent: dict
    gap: dict
    sums: list
    odd_counts: list
    high_counts: list
    acs: list
    past_sets: set = field(default_factory=set)

    @property
    def expected_recent(self):
        return min(RECENT, self.n_draws) * 6 / 45

    @property
    def avg_gap(self):
        return 45 / 6  # 번호 하나의 기대 출현 간격 ≈ 7.5회

    def hot_list(self, k=6):
        return sorted(range(1, 46), key=lambda n: (-self.recent[n], -self.freq[n]))[:k]

    def cold_list(self, k=6):
        return sorted(range(1, 46), key=lambda n: (-self.gap[n], self.freq[n]))[:k]

    def freq_rank(self, n):
        order = sorted(range(1, 46), key=lambda x: -self.freq[x])
        return order.index(n) + 1

    def share(self, values, pred):
        if not values:
            return None
        return 100 * sum(1 for v in values if pred(v)) / len(values)

    def sum_range(self):
        if len(self.sums) < 30:
            return 100, 175
        s = sorted(self.sums)
        return s[int(len(s) * 0.1)], s[int(len(s) * 0.9)]


def build_stats(draws):
    """draws: [(round, [6], bonus, date)] 오름차순"""
    freq, recent = Counter(), Counter()
    last_seen = {}
    for idx, (rnd, nums, _b, _d) in enumerate(draws):
        for n in nums:
            freq[n] += 1
            last_seen[n] = idx
    for _rnd, nums, _b, _d in draws[-RECENT:]:
        recent.update(nums)
    total = len(draws)
    gap = {n: (total - 1 - last_seen[n]) if n in last_seen else total for n in range(1, 46)}
    return LottoStats(
        n_draws=total,
        latest_round=draws[-1][0] if draws else None,
        last_draw=list(draws[-1][1]) if draws else [],
        freq={n: freq[n] for n in range(1, 46)},
        recent={n: recent[n] for n in range(1, 46)},
        gap=gap,
        sums=[sum(d[1]) for d in draws],
        odd_counts=[sum(n % 2 for n in d[1]) for d in draws],
        high_counts=[sum(n >= 23 for n in d[1]) for d in draws],
        acs=[ac_value(sorted(d[1])) for d in draws],
        past_sets={tuple(sorted(d[1])) for d in draws},
    )


# ---------- 생성 ----------
def _weights(stats, kind):
    if kind == "hot":
        return {n: (stats.recent[n] + 0.5) ** 1.6 for n in range(1, 46)}
    if kind == "cold":
        return {n: (stats.gap[n] + 1) ** 0.9 for n in range(1, 46)}
    return {n: 1.0 for n in range(1, 46)}


def _pick(weights, exclude, rng):
    pool = [n for n in weights if n not in exclude]
    return rng.choices(pool, weights=[weights[n] for n in pool], k=1)[0]


def _slot_plan(strategy, stats, rng):
    if strategy == "hot":
        return ["hot"] * 4 + ["uniform"] * 2
    if strategy == "cold":
        return ["cold"] * 4 + ["uniform"] * 2
    if strategy == "random":
        return ["uniform"] * 6
    plan = ["hot", "hot", "cold", "cold", "uniform", "uniform"]
    if stats.last_draw and rng.random() < 0.6:
        plan[4] = "carry"
    return plan


def _passes_filters(nums, stats, strategy):
    # 인기 패턴(당첨 시 나눠 가질 확률이 큰 조합) 회피는 모든 전략에 적용
    if max(nums) <= 31:            # 생일 번호만으로 구성
        return False
    if has_run(nums, 3):
        return False
    diffs = {b - a for a, b in zip(nums, nums[1:])}
    if len(diffs) == 1:            # 등차수열
        return False
    if tuple(nums) in stats.past_sets:
        return False
    if strategy == "random":
        return True
    lo, hi = stats.sum_range()
    if not lo <= sum(nums) <= hi:
        return False
    odd = sum(n % 2 for n in nums)
    if not 2 <= odd <= 4:
        return False
    high = sum(n >= 23 for n in nums)
    if not 2 <= high <= 4:
        return False
    if max(Counter(decade(n) for n in nums).values()) > 3:
        return False
    if max(Counter(n % 10 for n in nums).values()) > 2:
        return False
    if ac_value(nums) < 6:
        return False
    return True


def generate(stats, strategy="balanced", count=5, seed=None):
    rng = random.Random(seed)
    results = []
    attempts = 0
    while len(results) < count and attempts < 20000:
        attempts += 1
        plan = _slot_plan(strategy, stats, rng)
        chosen, source = [], {}
        for kind in plan:
            if kind == "carry":
                options = [n for n in stats.last_draw if n not in chosen]
                n = rng.choice(options)
            else:
                n = _pick(_weights(stats, kind), set(chosen), rng)
            chosen.append(n)
            source[n] = kind
        nums = sorted(chosen)
        if not _passes_filters(nums, stats, strategy):
            continue
        if any(len(set(nums) & set(r["numbers"])) > 2 for r in results):
            continue
        results.append({
            "numbers": nums,
            "reasons": [number_reason(n, source[n], stats) for n in nums],
            "metrics": set_metrics(nums, stats),
            "strategy": strategy,
        })
    return results


# ---------- 근거 문장 ----------
def number_reason(n, kind, stats):
    facts = []
    if stats.n_draws == 0:
        return {"n": n, "tag": "랜덤", "text": "당첨번호 데이터가 없어 규칙 필터만 적용한 무작위 선택"}
    exp = stats.expected_recent
    if kind == "carry":
        tag, head = "이월", f"직전 {stats.latest_round}회 당첨번호 이월"
    elif stats.recent[n] >= exp + 1.3:
        tag, head = "핫", f"최근 {min(RECENT, stats.n_draws)}회 중 {stats.recent[n]}회 출현 (평균 {exp:.1f}회)"
    elif stats.gap[n] >= 2 * stats.avg_gap:
        tag, head = "콜드", f"{stats.gap[n]}회 연속 미출현 (평균 출현 간격 약 {stats.avg_gap:.1f}회)"
    else:
        zone = "1~9" if n < 10 else f"{decade(n) * 10}번대"
        tag, head = "균형", f"{zone} 구간 균형 보충 (최근 {stats.recent[n]}회 출현 · 평균 수준)"
    if kind != "carry" and n in stats.last_draw:
        facts.append("직전 회차에도 나온 번호")
    elif kind != "carry" and any(abs(n - x) == 1 for x in stats.last_draw):
        nb = [x for x in stats.last_draw if abs(n - x) == 1][0]
        facts.append(f"직전 회차 {nb}의 이웃수")
    rank = stats.freq_rank(n)
    if rank <= 10:
        facts.append(f"역대 출현 {stats.freq[n]}회 · 전체 {rank}위")
    elif rank >= 36:
        facts.append(f"역대 출현 {stats.freq[n]}회 · 하위권({rank}위)")
    text = head + (" · " + " · ".join(facts) if facts else "")
    return {"n": n, "tag": tag, "text": text}


def set_metrics(nums, stats):
    s = sum(nums)
    odd = sum(n % 2 for n in nums)
    high = sum(n >= 23 for n in nums)
    ac = ac_value(nums)

    def line(label, values, pred, tail):
        p = stats.share(values, pred)
        return f"{label} → 역대 당첨조합의 {p:.0f}%가 {tail}" if p is not None else label

    return [
        line(f"합계 {s}", stats.sums, lambda v: s - 10 <= v <= s + 10, f"{s - 10}~{s + 10} 구간"),
        line(f"홀짝 {odd}:{6 - odd}", stats.odd_counts, lambda v: v == odd, "같은 비율"),
        line(f"저고(1~22 : 23~45) {6 - high}:{high}", stats.high_counts, lambda v: v == high, "같은 비율"),
        line(f"AC값 {ac} (번호 간격이 고르게 퍼진 정도)", stats.acs, lambda v: v >= ac, f"{ac} 이상"),
        "인기 패턴 회피: 1~31만으로 구성(생일 번호) X · 3연속 X · 등차수열 X",
    ]


def stats_summary_text(stats):
    """AI에게 넘길 통계 요약."""
    if stats.n_draws == 0:
        return "로또 당첨번호 데이터 없음."
    lo, hi = stats.sum_range()
    return (
        f"수집된 로또 회차: {stats.n_draws}개 (최신 {stats.latest_round}회, 당첨번호 {stats.last_draw})\n"
        f"최근 {RECENT}회 핫넘버 상위: {stats.hot_list(8)}\n"
        f"장기 미출현 상위(번호:미출현 회수): {[(n, stats.gap[n]) for n in stats.cold_list(8)]}\n"
        f"역대 출현 빈도 상위: {sorted(range(1, 46), key=lambda n: -stats.freq[n])[:8]}\n"
        f"역대 당첨 합계 10~90% 구간: {lo}~{hi}\n"
    )
