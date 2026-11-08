"""customtkinter 화면."""
import os
import queue
import subprocess
import sys
import threading
from tkinter import messagebox

import customtkinter as ctk

from . import APP_NAME, APP_VERSION, ai, analysis_lotto as AL, analysis_pension as AP, checker, db, fetcher, paths, rounds

FAMILY = "Malgun Gothic" if sys.platform == "win32" else None

# 색상 팔레트 (밝은 모드, 어두운 모드)
BG = ("#f3f4f8", "#111318")
CARD = ("#ffffff", "#1b1e26")
CARD2 = ("#f7f8fb", "#222632")
BORDER = ("#e3e6ee", "#2c313d")
TEXT = ("#1c1f26", "#e9ebf1")
MUTED = ("#6b7280", "#9aa1b1")
ACCENT = ("#5b5bd6", "#7c7cf0")
ACCENT_H = ("#4a4ac4", "#6a6ae0")
GOOD = ("#16a34a", "#22c55e")
WARN = ("#d97706", "#f59e0b")
BAD = ("#dc2626", "#f87171")

TAG_COLORS = {
    "핫": ("#ef4444", "#ffffff"),
    "콜드": ("#3b82f6", "#ffffff"),
    "이월": ("#a855f7", "#ffffff"),
    "균형": ("#10b981", "#ffffff"),
    "랜덤": ("#6b7280", "#ffffff"),
}
# 연금복권 자리별 색 (조, 1~6번째 자리)
PENSION_COLORS = ["#374151", "#ef4444", "#f97316", "#eab308", "#3b82f6", "#8b5cf6", "#6b7280"]
STRATEGY_LABELS = list(AL.STRATEGIES.values())
STRATEGY_KEYS = {v: k for k, v in AL.STRATEGIES.items()}


def F(size=13, weight="normal"):
    return ctk.CTkFont(family=FAMILY, size=size, weight=weight)


def ball_color(n):
    if n <= 10:
        return "#f6b500", "#1c1f26"
    if n <= 20:
        return "#3b9be8", "#ffffff"
    if n <= 30:
        return "#ef5b5b", "#ffffff"
    if n <= 40:
        return "#8f96a3", "#ffffff"
    return "#7cc142", "#ffffff"


class RoundLabel(ctk.CTkLabel):
    """모서리 둥근 라벨이 글자 양옆에 여백을 넣어 타원이 되는 것을 막음 (정원 유지)."""

    def _create_grid(self):
        super()._create_grid()
        self._label.grid_configure(padx=0)


def Ball(master, n, size=40):
    bg, fg = ball_color(n)
    lbl = RoundLabel(master, text=str(n), width=size, height=size, corner_radius=size // 2,
                       fg_color=bg, text_color=fg, font=F(int(size * 0.4), "bold"))
    return lbl


def Digit(master, d, pos, size=34):
    return ctk.CTkLabel(master, text=str(d), width=size, height=size, corner_radius=8,
                        fg_color=PENSION_COLORS[pos], text_color="#ffffff", font=F(int(size * 0.45), "bold"))


def Chip(master, text, color, fg="#ffffff", width=44):
    return RoundLabel(master, text=text, width=width, height=22, corner_radius=11,
                        fg_color=color, text_color=fg, font=F(11, "bold"))


def Card(master, **kw):
    return ctk.CTkFrame(master, fg_color=CARD, corner_radius=14, border_width=1, border_color=BORDER, **kw)


def clear(frame):
    for w in frame.winfo_children():
        w.destroy()


def open_folder(path):
    try:
        if sys.platform == "win32":
            os.startfile(path)  # noqa
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except OSError:
        messagebox.showinfo(APP_NAME, f"폴더 위치: {path}")


# ======================================================================
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode(db.get_setting("appearance", "dark"))
        ctk.set_default_color_theme("blue")
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("1180x800")
        self.minsize(1000, 680)
        self.configure(fg_color=BG)
        self.jobs = queue.Queue()
        self.busy = False

        self.lotto_stats = AL.build_stats(db.lotto_draws())
        self.pension_stats = AP.build_stats(db.pension_draws())

        self._build_header()
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=18, pady=(4, 0))
        self.views = {
            "로또 6/45": LottoView(self.body, self),
            "연금복권 720+": PensionView(self.body, self),
            "구매 내역 · 채점": HistoryView(self.body, self),
            "당첨번호 데이터": DataView(self.body, self),
        }
        self._build_statusbar()
        self.show("로또 6/45")
        self.after(100, self._poll_jobs)
        self.after(400, self.auto_update)

    # ---------- 레이아웃 ----------
    def _build_header(self):
        h = ctk.CTkFrame(self, fg_color="transparent")
        h.pack(fill="x", padx=18, pady=(16, 8))
        left = ctk.CTkFrame(h, fg_color="transparent")
        left.pack(side="left")
        ctk.CTkLabel(left, text="◆ " + APP_NAME, font=F(24, "bold"), text_color=TEXT).pack(anchor="w")
        self.sub = ctk.CTkLabel(left, text="", font=F(12), text_color=MUTED)
        self.sub.pack(anchor="w")

        right = ctk.CTkFrame(h, fg_color="transparent")
        right.pack(side="right")
        self.theme_btn = ctk.CTkButton(right, text="☀ / ☾", width=64, height=34, corner_radius=10,
                                       fg_color=CARD2, hover_color=BORDER, text_color=TEXT,
                                       command=self.toggle_theme, font=F(12))
        self.theme_btn.pack(side="right", padx=(8, 0))
        self.update_btn = ctk.CTkButton(right, text="⟳  당첨번호 업데이트", height=34, corner_radius=10,
                                        fg_color=ACCENT, hover_color=ACCENT_H, font=F(13, "bold"),
                                        command=self.auto_update)
        self.update_btn.pack(side="right")

        self.nav = ctk.CTkSegmentedButton(self, values=["로또 6/45", "연금복권 720+", "구매 내역 · 채점", "당첨번호 데이터"],
                                          command=self.show, font=F(14, "bold"), height=40, corner_radius=12,
                                          selected_color=ACCENT, selected_hover_color=ACCENT_H,
                                          unselected_color=CARD, unselected_hover_color=CARD2,
                                          fg_color=CARD, text_color=TEXT)
        self.nav.pack(fill="x", padx=18, pady=(0, 10))

    def _build_statusbar(self):
        bar = ctk.CTkFrame(self, fg_color=CARD, corner_radius=0, height=34)
        bar.pack(fill="x", side="bottom")
        self.status = ctk.CTkLabel(bar, text="", font=F(12), text_color=MUTED, anchor="w")
        self.status.pack(side="left", padx=14, pady=6)
        self.progress = ctk.CTkProgressBar(bar, width=220, height=8, progress_color=ACCENT)
        self.progress.set(0)
        self.refresh_header()

    def show(self, name):
        self.nav.set(name)
        for v in self.views.values():
            v.pack_forget()
        view = self.views[name]
        view.pack(fill="both", expand=True)
        if hasattr(view, "on_show"):
            view.on_show()

    def toggle_theme(self):
        mode = "light" if ctk.get_appearance_mode().lower() == "dark" else "dark"
        ctk.set_appearance_mode(mode)
        db.set_setting("appearance", mode)

    def refresh_header(self):
        ls, ps = self.lotto_stats, self.pension_stats
        lr = f"로또 {ls.latest_round}회까지 {ls.n_draws}개" if ls.n_draws else "로또 데이터 없음"
        pr = f"연금 {ps.latest_round}회까지 {ps.n_draws}개" if ps.n_draws else "연금 데이터 없음"
        self.sub.configure(text=f"다음 회차  로또 제 {rounds.lotto_next_round()}회 · 연금복권 제 {rounds.pension_next_round()}회      |      저장된 당첨번호: {lr} · {pr}")
        if not self.busy:
            self.set_status(f"데이터 폴더: {paths.data_dir()}")

    def set_status(self, text, ratio=None):
        self.status.configure(text=text)
        if ratio is None:
            self.progress.pack_forget()
        else:
            if not self.progress.winfo_ismapped():
                self.progress.pack(side="right", padx=14)
            self.progress.set(ratio)

    def reload_stats(self):
        self.lotto_stats = AL.build_stats(db.lotto_draws())
        self.pension_stats = AP.build_stats(db.pension_draws())
        self.refresh_header()
        for v in self.views.values():
            if hasattr(v, "on_data_changed"):
                v.on_data_changed()

    # ---------- 백그라운드 작업 ----------
    def run_bg(self, func, on_done, *args):
        def worker():
            try:
                res = func(*args)
                self.jobs.put((on_done, (True, res)))
            except Exception as e:  # noqa
                self.jobs.put((on_done, (False, f"{e.__class__.__name__}: {e}")))
        threading.Thread(target=worker, daemon=True).start()

    def _poll_jobs(self):
        try:
            while True:
                cb, arg = self.jobs.get_nowait()
                cb(*arg) if isinstance(arg, tuple) else cb(arg)
        except queue.Empty:
            pass
        self.after(100, self._poll_jobs)

    def auto_update(self):
        if self.busy:
            return
        self.busy = True
        self.update_btn.configure(state="disabled", text="수집 중…")
        self.set_status("인터넷 연결 확인 중…", 0)

        def job():
            if not fetcher.is_online():
                return {"offline": True}
            return fetcher.update_all(progress=lambda m, r: self.jobs.put((self.set_status, (m, r))))

        self.run_bg(job, self._update_done)

    def _update_done(self, ok, res):
        self.busy = False
        self.update_btn.configure(state="normal", text="⟳  당첨번호 업데이트")
        if not ok:
            self.set_status(f"수집 중 오류: {res}")
            return
        if res.get("offline"):
            self.set_status("인터넷 연결이 없어 저장된 데이터로 동작합니다.")
            return
        self.reload_stats()
        msg = f"수집 완료 · 로또 +{res['lotto_added']}회, 연금 +{res['pension_added']}회"
        if res["errors"]:
            msg += f" · 일부 실패 {len(res['errors'])}건 (‘당첨번호 데이터’ 탭에서 직접 입력 가능)"
            fetcher.log("\n".join(res["errors"][:20]))
        self.set_status(msg)
        self.views["구매 내역 · 채점"].refresh()

    # ---------- AI ----------
    def ask_ai(self, game, candidates_text, round_no):
        stats_text = AL.stats_summary_text(self.lotto_stats) if game == "lotto" else AP.stats_summary_text(self.pension_stats)
        prompt = ai.build_prompt(game, stats_text, candidates_text, round_no)
        if not ai.find_claude():
            self.copy_prompt(prompt, reason="이 PC에서 Claude Code를 찾지 못했습니다.")
            return
        win = AIWindow(self, "Claude 분석 중… (최대 몇 분 걸릴 수 있어요)")
        self.run_bg(ai.ask_claude, lambda ok, res: self._ai_done(win, prompt, ok, res), prompt)

    def _ai_done(self, win, prompt, ok, res):
        if not win.winfo_exists():
            return
        if ok and res[0]:
            win.set_text(res[1])
        else:
            err = res[1] if ok else res
            win.set_text(f"{err}\n\n대신 질문 내용을 클립보드에 복사했습니다. Claude 앱에 붙여넣어 물어보세요.")
            self.clipboard_clear()
            self.clipboard_append(prompt)

    def copy_prompt(self, prompt, reason=""):
        self.clipboard_clear()
        self.clipboard_append(prompt)
        messagebox.showinfo(APP_NAME, (reason + "\n\n" if reason else "") +
                            "AI에게 보낼 질문(통계 + 후보 번호)을 클립보드에 복사했습니다.\nClaude 앱에 붙여넣기(Ctrl+V) 하세요.")


class AIWindow(ctk.CTkToplevel):
    def __init__(self, master, text):
        super().__init__(master)
        self.title("Claude 분석")
        self.geometry("720x640")
        self.configure(fg_color=BG)
        self.after(50, self.lift)
        self.box = ctk.CTkTextbox(self, font=F(13), wrap="word", fg_color=CARD, text_color=TEXT,
                                  corner_radius=12, border_width=1, border_color=BORDER)
        self.box.pack(fill="both", expand=True, padx=14, pady=(14, 8))
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(0, 14))
        ctk.CTkButton(row, text="결과 복사", command=self.copy, fg_color=ACCENT, hover_color=ACCENT_H,
                      font=F(13, "bold")).pack(side="right")
        self.set_text(text)

    def set_text(self, text):
        self.box.configure(state="normal")
        self.box.delete("1.0", "end")
        self.box.insert("1.0", text)
        self.box.configure(state="disabled")

    def copy(self):
        self.clipboard_clear()
        self.clipboard_append(self.box.get("1.0", "end").strip())


def control_panel(parent, app, title, on_generate, on_ai, on_copy, note):
    """좌측 공통 패널. (패널, 전략 세그먼트, 통계 영역) 반환."""
    panel = ctk.CTkFrame(parent, fg_color="transparent", width=320)
    panel.pack(side="left", fill="y", padx=(0, 14))
    panel.pack_propagate(False)

    card = Card(panel)
    card.pack(fill="x")
    ctk.CTkLabel(card, text=title, font=F(16, "bold"), text_color=TEXT).pack(anchor="w", padx=16, pady=(14, 2))
    round_lbl = ctk.CTkLabel(card, text="", font=F(12), text_color=MUTED)
    round_lbl.pack(anchor="w", padx=16)
    ctk.CTkLabel(card, text="분석 전략", font=F(12, "bold"), text_color=MUTED).pack(anchor="w", padx=16, pady=(12, 4))
    seg = ctk.CTkSegmentedButton(card, values=STRATEGY_LABELS, font=F(12), height=32,
                                 selected_color=ACCENT, selected_hover_color=ACCENT_H)
    seg.set(STRATEGY_LABELS[0])
    seg.pack(fill="x", padx=16)
    ctk.CTkButton(card, text="번호 생성", height=44, corner_radius=12, font=F(15, "bold"),
                  fg_color=ACCENT, hover_color=ACCENT_H, command=on_generate).pack(fill="x", padx=16, pady=(14, 6))
    row = ctk.CTkFrame(card, fg_color="transparent")
    row.pack(fill="x", padx=16, pady=(0, 6))
    ctk.CTkButton(row, text="Claude AI 분석", height=34, corner_radius=10, font=F(12, "bold"),
                  fg_color="#d97757", hover_color="#c4643f", command=on_ai).pack(side="left", fill="x", expand=True, padx=(0, 4))
    ctk.CTkButton(row, text="질문 복사", height=34, width=90, corner_radius=10, font=F(12),
                  fg_color=CARD2, hover_color=BORDER, text_color=TEXT, command=on_copy).pack(side="left")
    ctk.CTkLabel(card, text=note, font=F(11), text_color=MUTED, justify="left", wraplength=285).pack(anchor="w", padx=16, pady=(4, 14))

    stats = Card(panel)
    stats.pack(fill="both", expand=True, pady=(12, 0))
    return panel, seg, stats, round_lbl


# ======================================================================
class LottoView(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.sets = []
        self.checks = []
        _, self.seg, self.stats_card, self.round_lbl = control_panel(
            self, app, "로또 6/45 · 5세트", self.generate, self.ai, self.copy,
            "추첨은 매 회 독립이라 어떤 분석도 당첨 확률을 바꾸지 못해요. 근거는 '과거 데이터와 이렇게 맞는다'는 설명이에요.")

        right = ctk.CTkFrame(self, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True)
        self.list = ctk.CTkScrollableFrame(right, fg_color="transparent")
        self.list.pack(fill="both", expand=True)
        bottom = Card(right)
        bottom.pack(fill="x", pady=(10, 0))
        self.sel_lbl = ctk.CTkLabel(bottom, text="", font=F(12), text_color=MUTED)
        self.sel_lbl.pack(side="left", padx=16, pady=12)
        self.confirm_btn = ctk.CTkButton(bottom, text="", height=40, corner_radius=10, font=F(14, "bold"),
                                         fg_color=GOOD, hover_color="#15803d", command=self.confirm)
        self.confirm_btn.pack(side="right", padx=12, pady=10)
        self.on_data_changed()
        self.generate()

    def on_data_changed(self):
        rnd = rounds.lotto_next_round()
        self.round_lbl.configure(text=f"제 {rnd}회 · {rounds.lotto_draw_date(rnd)} (토) 추첨")
        self.confirm_btn.configure(text=f"선택한 번호 구매 확정 · 제 {rnd}회")
        self._render_stats()

    def _render_stats(self):
        c = self.stats_card
        clear(c)
        st = self.app.lotto_stats
        ctk.CTkLabel(c, text="데이터 한눈에 보기", font=F(14, "bold"), text_color=TEXT).pack(anchor="w", padx=16, pady=(14, 6))
        if st.n_draws == 0:
            ctk.CTkLabel(c, text="저장된 당첨번호가 없어요.\n상단 '당첨번호 업데이트' 또는\n'당첨번호 데이터' 탭에서 입력하세요.",
                         font=F(12), text_color=MUTED, justify="left").pack(anchor="w", padx=16)
            return
        for title, nums in ((f"직전 {st.latest_round}회 당첨", st.last_draw),
                            (f"핫넘버 (최근 {min(AL.RECENT, st.n_draws)}회 최다)", st.hot_list(6)),
                            ("콜드넘버 (장기 미출현)", st.cold_list(6))):
            ctk.CTkLabel(c, text=title, font=F(12, "bold"), text_color=MUTED).pack(anchor="w", padx=16, pady=(8, 4))
            row = ctk.CTkFrame(c, fg_color="transparent")
            row.pack(anchor="w", padx=14)
            for n in nums:
                Ball(row, n, size=34).pack(side="left", padx=2)
        lo, hi = st.sum_range()
        ctk.CTkLabel(c, text=f"분석 데이터 {st.n_draws}회분 · 당첨 합계 주요 구간 {lo}~{hi}",
                     font=F(11), text_color=MUTED).pack(anchor="w", padx=16, pady=(12, 14))

    def generate(self):
        strategy = STRATEGY_KEYS[self.seg.get()]
        self.sets = AL.generate(self.app.lotto_stats, strategy)
        clear(self.list)
        self.checks = []
        for i, s in enumerate(self.sets):
            self._render_set(i, s)
        self._update_sel()

    def _render_set(self, i, s):
        card = Card(self.list)
        card.pack(fill="x", pady=(0, 12), padx=(0, 6))
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(14, 8))
        var = ctk.BooleanVar(value=False)
        self.checks.append(var)
        ctk.CTkCheckBox(top, text=f"SET {'ABCDE'[i]}", variable=var, font=F(15, "bold"), text_color=TEXT,
                        command=self._update_sel, checkbox_width=22, checkbox_height=22,
                        fg_color=GOOD, hover_color="#15803d").pack(side="left")
        balls = ctk.CTkFrame(top, fg_color="transparent")
        balls.pack(side="left", padx=18)
        for n in s["numbers"]:
            Ball(balls, n, size=42).pack(side="left", padx=3)

        body = ctk.CTkFrame(card, fg_color=CARD2, corner_radius=10)
        body.pack(fill="x", padx=16, pady=(0, 8))
        for r in s["reasons"]:
            row = ctk.CTkFrame(body, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=2)
            Ball(row, r["n"], size=24).pack(side="left")
            col = TAG_COLORS.get(r["tag"], ("#6b7280", "#fff"))
            Chip(row, r["tag"], col[0], col[1]).pack(side="left", padx=8)
            ctk.CTkLabel(row, text=r["text"], font=F(12), text_color=TEXT, anchor="w", justify="left").pack(side="left", fill="x")
        met = ctk.CTkFrame(card, fg_color="transparent")
        met.pack(fill="x", padx=18, pady=(2, 14))
        for m in s["metrics"]:
            ctk.CTkLabel(met, text="· " + m, font=F(11), text_color=MUTED, anchor="w").pack(anchor="w")

    def _selected(self):
        return [s for s, v in zip(self.sets, self.checks) if v.get()]

    def _update_sel(self):
        n = len(self._selected())
        self.sel_lbl.configure(text=f"구매한 세트를 체크한 뒤 확정하세요 · 선택 {n}세트 ({n * 1000:,}원)")

    def confirm(self):
        sel = self._selected()
        rnd = rounds.lotto_next_round()
        if not sel:
            messagebox.showinfo(APP_NAME, "구매한 세트를 먼저 체크하세요.")
            return
        lines = "\n".join(", ".join(map(str, s["numbers"])) for s in sel)
        if not messagebox.askyesno(APP_NAME, f"로또 제 {rnd}회로 {len(sel)}세트를 구매 확정할까요?\n\n{lines}"):
            return
        added = sum(db.add_purchase("lotto", rnd, ",".join(map(str, s["numbers"])), s["strategy"],
                                    [f"{r['n']}: [{r['tag']}] {r['text']}" for r in s["reasons"]]) for s in sel)
        messagebox.showinfo(APP_NAME, f"{added}세트 저장했어요. (중복 {len(sel) - added}세트 제외)\n추첨 후 '구매 내역 · 채점' 탭에서 자동으로 확인돼요.")
        for v in self.checks:
            v.set(False)
        self._update_sel()
        self.app.views["구매 내역 · 채점"].refresh()

    def _candidates_text(self):
        return "\n".join(f"SET {'ABCDE'[i]}: {s['numbers']}" for i, s in enumerate(self.sets))

    def ai(self):
        self.app.ask_ai("lotto", self._candidates_text(), rounds.lotto_next_round())

    def copy(self):
        prompt = ai.build_prompt("lotto", AL.stats_summary_text(self.app.lotto_stats), self._candidates_text(), rounds.lotto_next_round())
        self.app.copy_prompt(prompt)


# ======================================================================
class PensionView(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.tickets = {}
        self.checks = []
        _, self.seg, self.stats_card, self.round_lbl = control_panel(
            self, app, "연금복권 720+ · 조별 5개", self.generate, self.ai, self.copy,
            "1~5조마다 서로 다른 번호 5개씩(총 25개). 원하는 번호가 팔렸으면 같은 조의 다른 번호를 고르세요. "
            "25개 끝자리가 0~9를 모두 포함하도록 배치했어요.")
        right = ctk.CTkFrame(self, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True)
        self.list = ctk.CTkScrollableFrame(right, fg_color="transparent")
        self.list.pack(fill="both", expand=True)
        bottom = Card(right)
        bottom.pack(fill="x", pady=(10, 0))
        self.sel_lbl = ctk.CTkLabel(bottom, text="", font=F(12), text_color=MUTED)
        self.sel_lbl.pack(side="left", padx=16, pady=12)
        self.confirm_btn = ctk.CTkButton(bottom, text="", height=40, corner_radius=10, font=F(14, "bold"),
                                         fg_color=GOOD, hover_color="#15803d", command=self.confirm)
        self.confirm_btn.pack(side="right", padx=12, pady=10)
        self.on_data_changed()
        self.generate()

    def on_data_changed(self):
        rnd = rounds.pension_next_round()
        self.round_lbl.configure(text=f"제 {rnd}회 · {rounds.pension_draw_date(rnd)} (목) 추첨")
        self.confirm_btn.configure(text=f"선택한 번호 구매 확정 · 제 {rnd}회")
        self._render_stats()

    def _render_stats(self):
        c = self.stats_card
        clear(c)
        st = self.app.pension_stats
        ctk.CTkLabel(c, text="자리별 분석", font=F(14, "bold"), text_color=TEXT).pack(anchor="w", padx=16, pady=(14, 6))
        if st.n_draws == 0:
            ctk.CTkLabel(c, text="저장된 당첨번호가 없어요.\n상단 '당첨번호 업데이트' 또는\n'당첨번호 데이터' 탭에서 입력하세요.",
                         font=F(12), text_color=MUTED, justify="left").pack(anchor="w", padx=16)
            return
        g, num = st.last_draw
        ctk.CTkLabel(c, text=f"직전 {st.latest_round}회 1등", font=F(12, "bold"), text_color=MUTED).pack(anchor="w", padx=16, pady=(4, 4))
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(anchor="w", padx=14)
        Chip(row, f"{g}조", PENSION_COLORS[0], width=40).pack(side="left", padx=(0, 6))
        for p, ch in enumerate(num):
            Digit(row, ch, p + 1, size=28).pack(side="left", padx=2)
        ctk.CTkLabel(c, text="자리별 최근 최다 / 장기 미출현 숫자", font=F(12, "bold"), text_color=MUTED).pack(anchor="w", padx=16, pady=(12, 4))
        grid = ctk.CTkFrame(c, fg_color="transparent")
        grid.pack(anchor="w", padx=16)
        for p in range(6):
            hot = sorted(range(10), key=lambda d: -st.recent[p][d])[:2]
            cold = sorted(range(10), key=lambda d: -st.gap[p][d])[:2]
            ctk.CTkLabel(grid, text=f"{p + 1}번째", font=F(11), text_color=MUTED, width=46, anchor="w").grid(row=p, column=0, sticky="w")
            ctk.CTkLabel(grid, text=f"핫 {hot[0]}, {hot[1]}", font=F(11, "bold"), text_color="#ef4444", width=70, anchor="w").grid(row=p, column=1)
            ctk.CTkLabel(grid, text=f"콜드 {cold[0]}({st.gap[p][cold[0]]}회), {cold[1]}", font=F(11, "bold"), text_color="#3b82f6", anchor="w").grid(row=p, column=2, sticky="w")
        ctk.CTkLabel(c, text=f"분석 데이터 {st.n_draws}회분", font=F(11), text_color=MUTED).pack(anchor="w", padx=16, pady=(10, 14))

    def generate(self):
        strategy = STRATEGY_KEYS[self.seg.get()]
        self.tickets = AP.generate(self.app.pension_stats, strategy)
        clear(self.list)
        self.checks = []
        for grp, ts in self.tickets.items():
            card = Card(self.list)
            card.pack(fill="x", pady=(0, 12), padx=(0, 6))
            head = ctk.CTkFrame(card, fg_color="transparent")
            head.pack(fill="x", padx=16, pady=(12, 6))
            Chip(head, f"{grp}조", PENSION_COLORS[0], width=52).pack(side="left")
            ctk.CTkLabel(head, text=f"{grp}조 추천 5개", font=F(14, "bold"), text_color=TEXT).pack(side="left", padx=10)
            for t in ts:
                row = ctk.CTkFrame(card, fg_color=CARD2, corner_radius=10)
                row.pack(fill="x", padx=16, pady=3)
                var = ctk.BooleanVar(value=False)
                self.checks.append((var, t))
                ctk.CTkCheckBox(row, text="", variable=var, width=24, command=self._update_sel,
                                checkbox_width=22, checkbox_height=22, fg_color=GOOD, hover_color="#15803d").pack(side="left", padx=(10, 4), pady=8)
                Chip(row, f"{grp}조", PENSION_COLORS[0], width=40).pack(side="left", padx=(0, 8))
                for p, ch in enumerate(t["num"]):
                    Digit(row, ch, p + 1).pack(side="left", padx=2)
                summary = self._short_reason(t)
                ctk.CTkLabel(row, text=summary, font=F(11), text_color=MUTED, anchor="w").pack(side="left", padx=12)
                ctk.CTkButton(row, text="근거 보기", width=80, height=28, corner_radius=8, font=F(11),
                              fg_color=CARD, hover_color=BORDER, text_color=TEXT,
                              command=lambda t=t: self.show_reason(t)).pack(side="right", padx=10)
            ctk.CTkFrame(card, fg_color="transparent", height=8).pack()
        self._update_sel()

    @staticmethod
    def _short_reason(t):
        tags = [r.split("]")[0].split("[")[-1] for r in t["reasons"][:5] if "[" in r]
        cnt = {k: tags.count(k) for k in ("핫", "콜드", "균형") if tags.count(k)}
        return " · ".join(f"{k} {v}자리" for k, v in cnt.items()) + f" · 끝자리 {t['num'][-1]}"

    def show_reason(self, t):
        win = AIWindow(self.app, "")
        win.title(f"{t['grp']}조 {t['num']} 선택 근거")
        win.geometry("640x380")
        win.set_text(f"{t['grp']}조 {' '.join(t['num'])}\n\n" + "\n".join(t["reasons"]) +
                     "\n\n※ 추첨은 독립 시행이라 어떤 번호든 당첨 확률은 같아요.")

    def _selected(self):
        return [t for v, t in self.checks if v.get()]

    def _update_sel(self):
        n = len(self._selected())
        self.sel_lbl.configure(text=f"구매한 번호를 체크한 뒤 확정하세요 · 선택 {n}장 ({n * 1000:,}원)")

    def confirm(self):
        sel = self._selected()
        rnd = rounds.pension_next_round()
        if not sel:
            messagebox.showinfo(APP_NAME, "구매한 번호를 먼저 체크하세요.")
            return
        lines = "\n".join(f"{t['grp']}조 {t['num']}" for t in sel)
        if not messagebox.askyesno(APP_NAME, f"연금복권 제 {rnd}회로 {len(sel)}장을 구매 확정할까요?\n\n{lines}"):
            return
        added = sum(db.add_purchase("pension", rnd, f"{t['grp']}|{t['num']}", t["strategy"], t["reasons"]) for t in sel)
        messagebox.showinfo(APP_NAME, f"{added}장 저장했어요. (중복 {len(sel) - added}장 제외)\n추첨 후 '구매 내역 · 채점' 탭에서 자동으로 확인돼요.")
        for v, _ in self.checks:
            v.set(False)
        self._update_sel()
        self.app.views["구매 내역 · 채점"].refresh()

    def _candidates_text(self):
        return "\n".join(f"{g}조: {[t['num'] for t in ts]}" for g, ts in self.tickets.items())

    def ai(self):
        self.app.ask_ai("pension", self._candidates_text(), rounds.pension_next_round())

    def copy(self):
        prompt = ai.build_prompt("pension", AP.stats_summary_text(self.app.pension_stats), self._candidates_text(), rounds.pension_next_round())
        self.app.copy_prompt(prompt)


# ======================================================================
class HistoryView(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        top = Card(self)
        top.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(top, text="구매 내역 · 자동 채점", font=F(16, "bold"), text_color=TEXT).pack(side="left", padx=16, pady=14)
        self.summary = ctk.CTkLabel(top, text="", font=F(12), text_color=MUTED)
        self.summary.pack(side="left", padx=10)
        ctk.CTkButton(top, text="최신 결과로 다시 확인", height=34, corner_radius=10, font=F(12, "bold"),
                      fg_color=ACCENT, hover_color=ACCENT_H, command=self.app.auto_update).pack(side="right", padx=12)
        self.list = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.list.pack(fill="both", expand=True)
        self.refresh()

    def on_show(self):
        self.refresh()

    def on_data_changed(self):
        self.refresh()

    def refresh(self):
        clear(self.list)
        items = db.purchases()
        if not items:
            ctk.CTkLabel(self.list, text="아직 구매 확정한 번호가 없어요.\n로또/연금복권 탭에서 산 번호를 체크하고 '구매 확정'을 누르세요.",
                         font=F(13), text_color=MUTED, justify="center").pack(pady=60)
            self.summary.configure(text="")
            return
        groups = {}
        for p in items:
            groups.setdefault((p["round"], p["game"]), []).append(p)
        wins = pending = 0
        def draw_day(key):
            rnd, game = key
            return rounds.lotto_draw_date(rnd) if game == "lotto" else rounds.pension_draw_date(rnd)

        for (rnd, game), ps in sorted(groups.items(), key=lambda kv: draw_day(kv[0]), reverse=True):
            card = Card(self.list)
            card.pack(fill="x", pady=(0, 12), padx=(0, 6))
            head = ctk.CTkFrame(card, fg_color="transparent")
            head.pack(fill="x", padx=16, pady=(12, 6))
            if game == "lotto":
                draw = db.lotto_draw(rnd)
                Chip(head, "로또", "#f6b500", "#1c1f26", width=52).pack(side="left")
                ctk.CTkLabel(head, text=f"제 {rnd}회 · {rounds.lotto_draw_date(rnd)}", font=F(14, "bold"), text_color=TEXT).pack(side="left", padx=10)
                if draw:
                    ctk.CTkLabel(head, text="당첨번호", font=F(11), text_color=MUTED).pack(side="left", padx=(16, 6))
                    for n in draw[0]:
                        Ball(head, n, size=28).pack(side="left", padx=1)
                    ctk.CTkLabel(head, text="+", font=F(12, "bold"), text_color=MUTED).pack(side="left", padx=4)
                    Ball(head, draw[1], size=28).pack(side="left")
            else:
                draw = db.pension_draw(rnd)
                Chip(head, "연금", "#8b5cf6", width=52).pack(side="left")
                ctk.CTkLabel(head, text=f"제 {rnd}회 · {rounds.pension_draw_date(rnd)}", font=F(14, "bold"), text_color=TEXT).pack(side="left", padx=10)
                if draw:
                    ctk.CTkLabel(head, text="1등", font=F(11), text_color=MUTED).pack(side="left", padx=(16, 6))
                    Chip(head, f"{draw[0]}조", PENSION_COLORS[0], width=36).pack(side="left", padx=(0, 4))
                    for p, ch in enumerate(draw[1]):
                        Digit(head, ch, p + 1, size=24).pack(side="left", padx=1)
                    if draw[2]:
                        ctk.CTkLabel(head, text=f"보너스 {draw[2]}", font=F(11), text_color=MUTED).pack(side="left", padx=10)
            for p in ps:
                res = checker.check(p)
                if res["status"] == "pending":
                    pending += 1
                    color = ACCENT
                elif res["rank"] is not None:
                    wins += 1
                    color = GOOD
                else:
                    color = MUTED
                row = ctk.CTkFrame(card, fg_color=CARD2, corner_radius=10)
                row.pack(fill="x", padx=16, pady=3)
                nums = ctk.CTkFrame(row, fg_color="transparent")
                nums.pack(side="left", padx=10, pady=7)
                if game == "lotto":
                    hits = set(res.get("hits", []))
                    for n in map(int, p["numbers"].split(",")):
                        b = Ball(nums, n, size=30)
                        if res["status"] == "done" and n not in hits:
                            b.configure(fg_color=("#d1d5db", "#3a3f4b"), text_color=MUTED)
                        b.pack(side="left", padx=2)
                else:
                    grp, num = p["numbers"].split("|")
                    tail = res.get("tail", 0)
                    Chip(nums, f"{grp}조", PENSION_COLORS[0], width=36).pack(side="left", padx=(0, 4))
                    for i, ch in enumerate(num):
                        d = Digit(nums, ch, i + 1, size=26)
                        if res["status"] == "done" and i < 6 - tail:
                            d.configure(fg_color=("#d1d5db", "#3a3f4b"), text_color=MUTED)
                        d.pack(side="left", padx=1)
                ctk.CTkLabel(row, text=res["text"], font=F(12, "bold"), text_color=color).pack(side="left", padx=12)
                ctk.CTkButton(row, text="삭제", width=50, height=26, corner_radius=8, font=F(11),
                              fg_color="transparent", hover_color=BORDER, text_color=MUTED,
                              command=lambda pid=p["id"]: self.delete(pid)).pack(side="right", padx=8)
            ctk.CTkFrame(card, fg_color="transparent", height=8).pack()
        self.summary.configure(text=f"총 {len(items)}건 · 당첨 {wins}건 · 결과 대기 {pending}건")

    def delete(self, pid):
        if messagebox.askyesno(APP_NAME, "이 구매 기록을 삭제할까요?"):
            db.delete_purchase(pid)
            self.refresh()


# ======================================================================
class DataView(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        top = Card(scroll)
        top.pack(fill="x", pady=(0, 12))
        self.info = ctk.CTkLabel(top, text="", font=F(13), text_color=TEXT, justify="left")
        self.info.pack(side="left", padx=16, pady=14)
        btns = ctk.CTkFrame(top, fg_color="transparent")
        btns.pack(side="right", padx=12)
        ctk.CTkButton(btns, text="자동 수집", width=96, height=34, font=F(12, "bold"), fg_color=ACCENT,
                      hover_color=ACCENT_H, command=app.auto_update).pack(side="left", padx=3)
        ctk.CTkButton(btns, text="수집 테스트", width=96, height=34, font=F(12), fg_color=CARD2, text_color=TEXT,
                      hover_color=BORDER, command=self.diagnose).pack(side="left", padx=3)
        ctk.CTkButton(btns, text="데이터 폴더", width=96, height=34, font=F(12), fg_color=CARD2, text_color=TEXT,
                      hover_color=BORDER, command=lambda: open_folder(str(paths.data_dir()))).pack(side="left", padx=3)

        cols = ctk.CTkFrame(scroll, fg_color="transparent")
        cols.pack(fill="x")
        cols.grid_columnconfigure((0, 1), weight=1, uniform="c")
        self._lotto_form(cols).grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self._pension_form(cols).grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        self.on_data_changed()

    def on_data_changed(self):
        ls, ps = self.app.lotto_stats, self.app.pension_stats
        lmiss = rounds.lotto_latest_drawn() - ls.n_draws
        pmiss = rounds.pension_latest_drawn() - ps.n_draws
        self.info.configure(text=(
            f"로또: {ls.n_draws}회분 저장 (최신 {ls.latest_round or '-'}회 / 현재 {rounds.lotto_latest_drawn()}회까지 추첨됨, 빠진 회차 {max(lmiss, 0)}개)\n"
            f"연금복권: {ps.n_draws}회분 저장 (최신 {ps.latest_round or '-'}회 / 현재 {rounds.pension_latest_drawn()}회까지 추첨됨, 빠진 회차 {max(pmiss, 0)}개)"))
        if hasattr(self, "l_round"):
            for e, v in ((self.l_round, rounds.lotto_latest_drawn()), (self.p_round, rounds.pension_latest_drawn())):
                e.delete(0, "end")
                e.insert(0, str(v))

    def _entry(self, master, width, ph=""):
        return ctk.CTkEntry(master, width=width, height=34, font=F(13), placeholder_text=ph, justify="center")

    def _lotto_form(self, master):
        c = Card(master)
        ctk.CTkLabel(c, text="로또 당첨번호 직접 입력", font=F(15, "bold"), text_color=TEXT).pack(anchor="w", padx=16, pady=(14, 8))
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(anchor="w", padx=16)
        ctk.CTkLabel(row, text="회차", font=F(12), text_color=MUTED).pack(side="left")
        self.l_round = self._entry(row, 70)
        self.l_round.pack(side="left", padx=(6, 12))
        self.l_nums = [self._entry(row, 44) for _ in range(6)]
        for e in self.l_nums:
            e.pack(side="left", padx=2)
        ctk.CTkLabel(row, text="+", font=F(14, "bold"), text_color=MUTED).pack(side="left", padx=4)
        self.l_bonus = self._entry(row, 60, "보너스")
        self.l_bonus.pack(side="left")
        ctk.CTkButton(c, text="저장", height=34, font=F(12, "bold"), fg_color=ACCENT, hover_color=ACCENT_H,
                      command=self.save_lotto).pack(anchor="e", padx=16, pady=8)
        ctk.CTkLabel(c, text="여러 회차 한꺼번에 붙여넣기 — 한 줄에 '회차 번호6개 보너스'\n예) 1249 3 11 19 27 35 42 8",
                     font=F(11), text_color=MUTED, justify="left").pack(anchor="w", padx=16)
        self.l_bulk = ctk.CTkTextbox(c, height=120, font=F(12), fg_color=CARD2, border_width=1, border_color=BORDER)
        self.l_bulk.pack(fill="x", padx=16, pady=6)
        ctk.CTkButton(c, text="일괄 저장", height=34, font=F(12, "bold"), fg_color=CARD2, text_color=TEXT,
                      hover_color=BORDER, command=self.bulk_lotto).pack(anchor="e", padx=16, pady=(0, 14))
        return c

    def _pension_form(self, master):
        c = Card(master)
        ctk.CTkLabel(c, text="연금복권 당첨번호 직접 입력", font=F(15, "bold"), text_color=TEXT).pack(anchor="w", padx=16, pady=(14, 8))
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(anchor="w", padx=16)
        ctk.CTkLabel(row, text="회차", font=F(12), text_color=MUTED).pack(side="left")
        self.p_round = self._entry(row, 70)
        self.p_round.pack(side="left", padx=(6, 12))
        self.p_grp = ctk.CTkOptionMenu(row, values=[f"{i}조" for i in range(1, 6)], width=72, height=34, font=F(12),
                                       fg_color=ACCENT, button_color=ACCENT_H)
        self.p_grp.pack(side="left", padx=(0, 6))
        self.p_num = self._entry(row, 110, "6자리")
        self.p_num.pack(side="left", padx=2)
        self.p_bonus = self._entry(row, 110, "보너스 6자리")
        self.p_bonus.pack(side="left", padx=6)
        ctk.CTkButton(c, text="저장", height=34, font=F(12, "bold"), fg_color=ACCENT, hover_color=ACCENT_H,
                      command=self.save_pension).pack(anchor="e", padx=16, pady=8)
        ctk.CTkLabel(c, text="여러 회차 한꺼번에 붙여넣기 — 한 줄에 '회차 조 6자리 [보너스6자리]'\n예) 340 3 517204 882913",
                     font=F(11), text_color=MUTED, justify="left").pack(anchor="w", padx=16)
        self.p_bulk = ctk.CTkTextbox(c, height=120, font=F(12), fg_color=CARD2, border_width=1, border_color=BORDER)
        self.p_bulk.pack(fill="x", padx=16, pady=6)
        ctk.CTkButton(c, text="일괄 저장", height=34, font=F(12, "bold"), fg_color=CARD2, text_color=TEXT,
                      hover_color=BORDER, command=self.bulk_pension).pack(anchor="e", padx=16, pady=(0, 14))
        return c

    def save_lotto(self):
        try:
            rnd = int(self.l_round.get())
            nums = [int(e.get()) for e in self.l_nums]
            bonus = int(self.l_bonus.get())
            db.upsert_lotto(rnd, str(rounds.lotto_draw_date(rnd)), nums, bonus)
        except ValueError as e:
            messagebox.showerror(APP_NAME, f"입력값을 확인하세요.\n{e}")
            return
        for e in self.l_nums + [self.l_bonus]:
            e.delete(0, "end")
        self.app.reload_stats()
        messagebox.showinfo(APP_NAME, f"로또 {rnd}회 저장 완료")

    def save_pension(self):
        try:
            rnd = int(self.p_round.get())
            grp = int(self.p_grp.get()[0])
            db.upsert_pension(rnd, str(rounds.pension_draw_date(rnd)), grp, self.p_num.get().strip(), self.p_bonus.get().strip() or None)
        except ValueError as e:
            messagebox.showerror(APP_NAME, f"입력값을 확인하세요.\n{e}")
            return
        self.p_num.delete(0, "end")
        self.p_bonus.delete(0, "end")
        self.app.reload_stats()
        messagebox.showinfo(APP_NAME, f"연금복권 {rnd}회 저장 완료")

    def bulk_lotto(self):
        rows, bad = fetcher.parse_lotto_lines(self.l_bulk.get("1.0", "end"))
        for rnd, nums, bonus in rows:
            db.upsert_lotto(rnd, str(rounds.lotto_draw_date(rnd)), nums, bonus)
        self._bulk_done(len(rows), bad, self.l_bulk)

    def bulk_pension(self):
        rows, bad = fetcher.parse_pension_lines(self.p_bulk.get("1.0", "end"))
        for rnd, grp, num, bonus in rows:
            db.upsert_pension(rnd, str(rounds.pension_draw_date(rnd)), grp, num, bonus)
        self._bulk_done(len(rows), bad, self.p_bulk)

    def _bulk_done(self, n, bad, box):
        self.app.reload_stats()
        msg = f"{n}개 회차 저장 완료"
        if bad:
            msg += f"\n\n형식이 맞지 않아 건너뛴 줄 {len(bad)}개:\n" + "\n".join(bad[:10])
            box.delete("1.0", "end")
            box.insert("1.0", "\n".join(bad))
        else:
            box.delete("1.0", "end")
        messagebox.showinfo(APP_NAME, msg)

    def diagnose(self):
        self.app.set_status("수집 테스트 중…", 0.5)
        self.app.run_bg(fetcher.diagnose, self._diag_done)

    def _diag_done(self, ok, res):
        self.app.set_status("수집 테스트 완료")
        messagebox.showinfo("수집 테스트", (res if ok else f"오류: {res}") + f"\n\n자세한 기록: {paths.log_path()}")


def main():
    app = App()
    app.mainloop()
