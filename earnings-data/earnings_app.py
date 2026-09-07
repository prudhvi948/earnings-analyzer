import matplotlib
matplotlib.use("TkAgg")
import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import os

plt.style.use("dark_background")

class EarningsApp:
    def __init__(self, root, ticker=None):
        self.root = root
        root.title("Earnings Gap Analyzer")
        root.geometry("1100x850")
        root.configure(bg="#0d1117")
        root.resizable(True, True)

        title = tk.Label(root, text="Earnings Gap Analyzer", font=("Segoe UI", 18, "bold"),
                         fg="white", bg="#0d1117")
        title.pack(pady=(15, 5))

        # Input row
        frame = tk.Frame(root, bg="#0d1117")
        frame.pack(pady=5)

        tk.Label(frame, text="Ticker:", font=("Segoe UI", 12), fg="#8b949e", bg="#0d1117")\
            .pack(side=tk.LEFT, padx=5)

        self.ticker_entry = tk.Entry(frame, font=("Segoe UI", 12), width=10, bg="#161b22",
                                       fg="white", insertbackground="white", relief=tk.FLAT,
                                       highlightthickness=1, highlightbackground="#30363d")
        self.ticker_entry.insert(0, (ticker or "NVDA").upper())
        self.ticker_entry.pack(side=tk.LEFT, padx=5)

        self.run_btn = tk.Button(frame, text="Run Analysis", font=("Segoe UI", 11, "bold"),
                                  bg="#238636", fg="white", padx=15, relief=tk.FLAT,
                                  activebackground="#2ea043", cursor="hand2",
                                  command=self.run_analysis)
        self.run_btn.pack(side=tk.LEFT, padx=10)

        self.status = tk.Label(root, text="Ready", font=("Segoe UI", 10), fg="#8b949e",
                                bg="#0d1117", anchor="w")
        self.status.pack(fill=tk.X, padx=15, pady=(0, 5))

        # Paned window: top=table, bottom=chart
        paned = tk.PanedWindow(root, orient=tk.VERTICAL, bg="#0d1117", sashwidth=4, sashrelief=tk.FLAT)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Table frame
        table_frame = tk.Frame(paned, bg="#0d1117")
        paned.add(table_frame, height=200)

        columns = ("date", "pre_close", "post_open", "move", "beat", "eps_actual", "eps_est")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=8)
        self.tree.heading("date", text="Date")
        self.tree.heading("pre_close", text="Pre-Close")
        self.tree.heading("post_open", text="Post-Open")
        self.tree.heading("move", text="Move %")
        self.tree.heading("beat", text="Beat")
        self.tree.heading("eps_actual", text="Actual EPS")
        self.tree.heading("eps_est", text="Est EPS")

        for col in columns:
            self.tree.column(col, anchor="center", width=100)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", background="#161b22", foreground="white",
                        fieldbackground="#161b22", font=("Segoe UI", 9))
        style.configure("Treeview.Heading", background="#21262d", foreground="#8b949e",
                        font=("Segoe UI", 9, "bold"))
        style.map("Treeview.Heading", background=[("active", "#30363d")])

        vsb = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        # Chart frame
        chart_frame = tk.Frame(paned, bg="#0d1117")
        paned.add(chart_frame, height=500)

        self.chart_frame = chart_frame

        # Stats bar
        self.stats_var = tk.StringVar()
        stats_bar = tk.Label(root, textvariable=self.stats_var, font=("Segoe UI", 10),
                              fg="#8b949e", bg="#0d1117", anchor="w", relief=tk.FLAT)
        stats_bar.pack(fill=tk.X, padx=15, pady=(0, 10))

        # Run initial analysis
        self.root.after(500, self.run_analysis)

    def run_analysis(self):
        ticker = self.ticker_entry.get().strip().upper()
        if not ticker:
            messagebox.showerror("Error", "Enter a ticker")
            return

        self.run_btn.config(state=tk.DISABLED, text="Running...")
        self.status.config(text=f"Fetching {ticker} earnings data...")
        threading.Thread(target=self._fetch_and_display, args=(ticker,), daemon=True).start()

    def _fetch_and_display(self, ticker):
        try:
            stock = yf.Ticker(ticker)
            earnings = stock.earnings_dates
            if earnings is None or earnings.empty:
                self.root.after(0, lambda: messagebox.showerror("Error", f"No earnings data for {ticker}"))
                self._reset_btn()
                return

            dates = []
            for idx in earnings.index:
                if isinstance(idx, pd.Timestamp):
                    dates.append(idx.to_pydatetime())
            dates = sorted(dates)

            results = []
            for ed in dates:
                earn_str = ed.strftime("%Y-%m-%d")
                pre_day = ed - timedelta(days=1)
                while pre_day.weekday() >= 5:
                    pre_day -= timedelta(days=1)
                post_day = ed + timedelta(days=1)
                while post_day.weekday() >= 5:
                    post_day += timedelta(days=1)
                start = (pre_day - timedelta(days=2)).strftime("%Y-%m-%d")
                end = (post_day + timedelta(days=2)).strftime("%Y-%m-%d")
                hist = stock.history(start=start, end=end, interval="1d")
                if hist.empty:
                    continue
                pre_close = post_open = None
                for dt, row in hist.iterrows():
                    d = dt.strftime("%Y-%m-%d")
                    if d == pre_day.strftime("%Y-%m-%d"):
                        pre_close = row["Close"]
                    if d == post_day.strftime("%Y-%m-%d"):
                        post_open = row["Open"]
                if pre_close is None or post_open is None:
                    continue
                move_pct = ((post_open - pre_close) / pre_close) * 100
                eps_actual = earnings.loc[ed, "Reported EPS"] if ed in earnings.index else None
                eps_est = earnings.loc[ed, "EPS Estimate"] if ed in earnings.index else None
                beat = ""
                if eps_actual is not None and eps_est is not None:
                    beat = "BEAT" if eps_actual > eps_est else "MISS"
                results.append({
                    "date": earn_str, "pre_close": pre_close,
                    "post_open": post_open, "move_pct": move_pct,
                    "beat": beat, "eps_actual": eps_actual, "eps_estimate": eps_est
                })

            if not results:
                self.root.after(0, lambda: messagebox.showerror("Error", "No results found"))
                self._reset_btn()
                return

            df = pd.DataFrame(results)
            self.root.after(0, self._update_table, df, ticker)
            self.root.after(0, self._update_chart, df, stock, ticker)
            self.root.after(0, self._update_stats, df)
            self.root.after(0, lambda: self.status.config(text=f"Done — {len(df)} earnings events for {ticker}"))

        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Error", str(e)))
        finally:
            self.root.after(0, self._reset_btn)

    def _reset_btn(self):
        self.run_btn.config(state=tk.NORMAL, text="Run Analysis")

    def _update_table(self, df, ticker):
        for row in self.tree.get_children():
            self.tree.delete(row)
        for _, r in df.iterrows():
            move_str = f"{r['move_pct']:+.2f}%"
            tags = ("up",) if r["move_pct"] > 0 else ("dn",)
            self.tree.insert("", tk.END, values=(
                r["date"], f"${r['pre_close']:.2f}", f"${r['post_open']:.2f}",
                move_str, r["beat"],
                f"{r['eps_actual']:.2f}" if pd.notna(r['eps_actual']) else "N/A",
                f"{r['eps_estimate']:.2f}" if pd.notna(r['eps_estimate']) else "N/A"
            ), tags=tags)
        self.tree.tag_configure("up", foreground="#22c55e")
        self.tree.tag_configure("dn", foreground="#ef4444")

    def _update_stats(self, df):
        n = len(df)
        avg = df["move_pct"].mean()
        med = df["move_pct"].median()
        up = (df["move_pct"] > 0).sum()
        dn = n - up
        self.stats_var.set(
            f"Total: {n}  |  Avg: {avg:+.2f}%  |  Median: {med:+.2f}%  |  "
            f"Max: {df['move_pct'].max():+.2f}%  |  Min: {df['move_pct'].min():+.2f}%  |  "
            f"Std: {df['move_pct'].std():.2f}%  |  Up: {up}/{n} ({up/n*100:.0f}%)  |  "
            f"Down: {dn}/{n} ({dn/n*100:.0f}%)"
        )

    def _update_chart(self, df, stock, ticker):
        for w in self.chart_frame.winfo_children():
            w.destroy()

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 5.5),
                                        gridspec_kw={"height_ratios": [2.5, 1]})
        fig.patch.set_facecolor("#0d1117")

        n = len(df)
        colors = ["#22c55e" if m > 0 else "#ef4444" for m in df["move_pct"]]
        dates_labels = [d[-5:] for d in df["date"]]

        ax1.bar(range(n), df["move_pct"], color=colors, width=0.7, edgecolor="none")
        ax1.axhline(0, color="#30363d", linewidth=1)
        ax1.set_xticks(range(n))
        ax1.set_xticklabels(dates_labels, rotation=45, ha="right", fontsize=8, color="#8b949e")
        ax1.set_ylabel("Gap %", fontsize=10, color="#8b949e")
        ax1.tick_params(axis="y", colors="#8b949e", labelsize=8)
        ax1.set_facecolor("#0d1117")
        for s in ax1.spines.values():
            s.set_color("#30363d")

        for i, v in enumerate(df["move_pct"]):
            y_pos = v + (0.5 if v >= 0 else -1.5)
            ax1.text(i, y_pos, f"{v:+.1f}%", ha="center", va="bottom" if v >= 0 else "top",
                     fontsize=7, fontweight="bold", color=colors[i])

        stats_text = (
            f"Total: {n} | Avg: {df['move_pct'].mean():+.1f}% | "
            f"Up: {(df['move_pct']>0).sum()}/{n} ({(df['move_pct']>0).sum()/n*100:.0f}%)"
        )
        ax1.text(0.98, 0.95, stats_text, transform=ax1.transAxes, fontsize=8,
                 color="#8b949e", va="top", ha="right",
                 bbox=dict(boxstyle="round,pad=0.3", facecolor="#161b22",
                           edgecolor="#30363d", alpha=0.9))

        # Price chart
        price_start = (datetime.strptime(df["date"].iloc[0], "%Y-%m-%d") - timedelta(days=5)).strftime("%Y-%m-%d")
        price_end = (datetime.strptime(df["date"].iloc[-1], "%Y-%m-%d") + timedelta(days=5)).strftime("%Y-%m-%d")
        try:
            price_hist = stock.history(start=price_start, end=price_end, interval="1d")
            if not price_hist.empty:
                ax2.plot(price_hist.index, price_hist["Close"], color="#2d7aff", linewidth=1.2)
                ax2.fill_between(price_hist.index, price_hist["Close"], alpha=0.1, color="#2d7aff")
                for ed in df["date"]:
                    dt = datetime.strptime(ed, "%Y-%m-%d")
                    ax2.axvline(x=dt, color="#ffc94d", linewidth=0.5, linestyle="--", alpha=0.3)
        except:
            pass

        ax2.set_ylabel("Price", fontsize=10, color="#8b949e")
        ax2.tick_params(axis="y", colors="#8b949e", labelsize=8)
        ax2.tick_params(axis="x", colors="#8b949e", labelsize=8)
        ax2.set_facecolor("#0d1117")
        for s in ax2.spines.values():
            s.set_color("#30363d")

        plt.tight_layout()

        canvas = FigureCanvasTkAgg(fig, self.chart_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)


def open_in_window(ticker):
    win = tk.Toplevel()
    EarningsApp(win, ticker=ticker)
    return win


if __name__ == "__main__":
    root = tk.Tk()
    app = EarningsApp(root)
    root.mainloop()
