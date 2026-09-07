import calendar as cal
import json
import threading
import time
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from io import StringIO
from pathlib import Path
from tkinter import messagebox

import pandas as pd
import requests
import yfinance as yf

from earnings_app import open_in_window

BG = "#0d1117"
PANEL = "#161b22"
BORDER = "#30363d"
FG = "white"
MUTED = "#8b949e"
ACCENT = "#238636"
WATCHLIST_BG = "#21262d"
WATCHLIST_FG = "#79c0ff"
VALUE_BG = "#3d2e04"
VALUE_FG = "#ffc94d"
NDAQ_BG = "#2d2349"
NDAQ_FG = "#d2a8ff"
MUST_BG = "#4a1526"
MUST_FG = "#ff9da6"

HERE = Path(__file__).resolve().parent
WATCHLIST_PATH = HERE.parent / "data" / "SPMO.csv"
SP500_CSV_PATH = HERE.parent / "data" / "SNP500.csv"
NASDAQ100_CSV_PATH = HERE.parent / "data" / "NASDAQ100.csv"
CACHE_PATH = HERE / "value_scan_cache.json"
EARNINGS_CACHE_PATH = HERE / "earnings_cache.json"
SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
NASDAQ100_URL = "https://en.wikipedia.org/wiki/List_of_NASDAQ-100_companies"
SP500_MAX_AGE_DAYS = 7
EARNINGS_CACHE_MAX_AGE_DAYS = 7

MAX_WORKERS = 12
LOW_THRESHOLD_PCT = 5.0
DAYS_52W = 252
DAYS_MULTI_YEAR = 756  # ~3 trading years


def load_watchlist(path=WATCHLIST_PATH):
    df = pd.read_csv(path)
    tickers = []
    for raw in df["Ticker"]:
        t = str(raw).strip().strip('"').upper()
        if t and t not in tickers:
            tickers.append(t)
    return tickers


def add_one_month(d):
    year, month = d.year, d.month + 1
    if month > 12:
        year, month = year + 1, 1
    day = min(d.day, cal.monthrange(year, month)[1])
    return date(year, month, day)


def earnings_dates_upcoming(ticker):
    try:
        dates = yf.Ticker(ticker).earnings_dates
        if dates is None or dates.empty:
            return ticker, []
        today = date.today()
        found = sorted({idx.date() for idx in dates.index
                        if isinstance(idx, pd.Timestamp) and idx.date() >= today})
        return ticker, found
    except Exception:
        return ticker, []


def _load_earnings_cache():
    try:
        return json.loads(EARNINGS_CACHE_PATH.read_text())
    except Exception:
        return {}


def _save_earnings_cache(cache):
    try:
        EARNINGS_CACHE_PATH.write_text(json.dumps(cache))
    except Exception:
        pass


def _cache_entry_valid(entry, today):
    if not entry:
        return False
    try:
        fetched = date.fromisoformat(entry["fetched"])
        cached_dates = [date.fromisoformat(d) for d in entry.get("dates", [])]
    except Exception:
        return False
    if fetched >= today:
        return True
    if (today - fetched).days > EARNINGS_CACHE_MAX_AGE_DAYS:
        return False
    return any(d >= today for d in cached_dates)


def fetch_sp500_constituents():
    resp = requests.get(SP500_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    resp.raise_for_status()
    table = pd.read_html(StringIO(resp.text))[0]
    df = table[["Symbol", "Security", "GICS Sector"]].rename(
        columns={"Symbol": "Ticker", "Security": "Company", "GICS Sector": "Sector"})
    df["Ticker"] = df["Ticker"].astype(str).str.replace(".", "-", regex=False)\
        .str.strip().str.upper()
    df["Company"] = df["Company"].astype(str).str.strip()
    df["Sector"] = df["Sector"].astype(str).str.strip()
    return df


def fetch_nasdaq100_constituents():
    resp = requests.get(NASDAQ100_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    resp.raise_for_status()
    for table in pd.read_html(StringIO(resp.text)):
        if "Ticker" in table.columns and "Company" in table.columns:
            sector_col = next((c for c in table.columns
                               if str(c).startswith(("GICS Sector", "ICB Industry"))), None)
            cols = ["Ticker", "Company"] + ([sector_col] if sector_col else [])
            df = table[cols].rename(columns={sector_col: "Sector"} if sector_col else {}).copy()
            df["Ticker"] = df["Ticker"].astype(str).str.replace(".", "-", regex=False)\
                .str.strip().str.upper()
            df["Company"] = df["Company"].astype(str).str.strip()
            return df
    raise ValueError("Nasdaq-100 components table not found")


def _update_constituents_csv(path, fetch_fn, max_age_days=SP500_MAX_AGE_DAYS, force=False):
    """Return tickers from a local constituents CSV, refreshing it from the web
    when it is missing or older than max_age_days (weekly update)."""
    stale = force or not path.exists() or \
        (time.time() - path.stat().st_mtime) > max_age_days * 86400
    if stale:
        try:
            df = fetch_fn()
            df.to_csv(path, index=False)
            return df["Ticker"].tolist()
        except Exception:
            if not path.exists():
                raise
    return load_watchlist(path)


def update_sp500_csv(path=SP500_CSV_PATH, max_age_days=SP500_MAX_AGE_DAYS, force=False):
    return _update_constituents_csv(path, fetch_sp500_constituents, max_age_days, force)


def update_nasdaq100_csv(path=NASDAQ100_CSV_PATH, max_age_days=SP500_MAX_AGE_DAYS, force=False):
    return _update_constituents_csv(path, fetch_nasdaq100_constituents, max_age_days, force)


def scan_value_buys(tickers, threshold=LOW_THRESHOLD_PCT):
    data = yf.download(tickers, period="5y", interval="1d", group_by="ticker",
                       threads=True, progress=False, auto_adjust=True)
    results = {}
    for t in tickers:
        try:
            close = data[t]["Close"].dropna()
            if len(close) < DAYS_52W:
                continue
            current = close.iloc[-1]
            low_52w = close.tail(DAYS_52W).min()
            pct_52w = (current - low_52w) / low_52w * 100
            pct_multi = None
            if len(close) >= DAYS_MULTI_YEAR:
                low_multi = close.tail(DAYS_MULTI_YEAR).min()
                pct_multi = (current - low_multi) / low_multi * 100
            if pct_multi is not None and pct_multi <= threshold:
                results[t] = {"tag": "multi-yr low", "pct_above_low": round(pct_multi, 1)}
            elif pct_52w <= threshold:
                results[t] = {"tag": "52w low", "pct_above_low": round(pct_52w, 1)}
        except Exception:
            continue
    return results


def load_cached_scan():
    try:
        cache = json.loads(CACHE_PATH.read_text())
        if cache.get("scan_date") == date.today().isoformat() and \
                cache.get("threshold") == LOW_THRESHOLD_PCT:
            return cache.get("results", {})
    except Exception:
        pass
    return None


def save_cached_scan(results):
    try:
        CACHE_PATH.write_text(json.dumps({
            "scan_date": date.today().isoformat(),
            "threshold": LOW_THRESHOLD_PCT,
            "results": results,
        }))
    except Exception:
        pass


class EarningsCalendarApp:
    def __init__(self, root):
        self.root = root
        root.title("Earnings Calendar")
        root.geometry("1400x900")
        root.configure(bg=BG)

        tk.Label(root, text="Earnings Calendar", font=("Segoe UI", 18, "bold"),
                 fg=FG, bg=BG).pack(pady=(15, 5))

        bar = tk.Frame(root, bg=BG)
        bar.pack(pady=5)

        tk.Label(bar, text="Start date:", font=("Segoe UI", 11), fg=MUTED, bg=BG)\
            .pack(side=tk.LEFT, padx=5)
        self.date_entry = tk.Entry(bar, font=("Segoe UI", 11), width=11, bg=PANEL, fg=FG,
                                   insertbackground=FG, relief=tk.FLAT, highlightthickness=1,
                                   highlightbackground=BORDER)
        self.date_entry.insert(0, date.today().strftime("%Y-%m-%d"))
        self.date_entry.pack(side=tk.LEFT, padx=5)

        self.load_btn = tk.Button(bar, text="Load Calendar", font=("Segoe UI", 11, "bold"),
                                  bg=ACCENT, fg=FG, padx=15, relief=tk.FLAT,
                                  activebackground="#2ea043", cursor="hand2",
                                  command=self.load_calendar)
        self.load_btn.pack(side=tk.LEFT, padx=10)

        self.value_var = tk.BooleanVar(value=True)
        tk.Checkbutton(bar, text="Include S&P 500 value buys (near 52w / multi-yr lows)",
                       variable=self.value_var, font=("Segoe UI", 10), fg=VALUE_FG, bg=BG,
                       selectcolor=PANEL, activebackground=BG, activeforeground=VALUE_FG)\
            .pack(side=tk.LEFT, padx=10)

        legend = tk.Frame(root, bg=BG)
        legend.pack(fill=tk.X, padx=15)
        tk.Label(legend, text="■ Watchlist (SPMO)", font=("Segoe UI", 9),
                 fg=WATCHLIST_FG, bg=BG).pack(side=tk.LEFT, padx=(0, 15))
        tk.Label(legend, text="■ Nasdaq 100", font=("Segoe UI", 9), fg=NDAQ_FG, bg=BG)\
            .pack(side=tk.LEFT, padx=(0, 15))
        tk.Label(legend, text="■ Value buy (near 52w / multi-yr low)", font=("Segoe UI", 9),
                 fg=VALUE_FG, bg=BG).pack(side=tk.LEFT, padx=(0, 15))
        tk.Label(legend, text="■ Must watch (SPMO + S&P 500 + Nasdaq 100)",
                 font=("Segoe UI", 9), fg=MUST_FG, bg=BG).pack(side=tk.LEFT)

        self.status = tk.Label(root, text="Ready", font=("Segoe UI", 10), fg=MUTED,
                               bg=BG, anchor="w")
        self.status.pack(fill=tk.X, padx=15, pady=(2, 5))

        container = tk.Frame(root, bg=BG)
        container.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.canvas = tk.Canvas(container, bg=BG, highlightthickness=0)
        vsb = tk.Scrollbar(container, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.grid_frame = tk.Frame(self.canvas, bg=BG)
        self.grid_window = self.canvas.create_window((0, 0), window=self.grid_frame, anchor="nw")
        self.grid_frame.bind("<Configure>",
                             lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfig(self.grid_window, width=e.width))
        container.bind("<Enter>", lambda e: self.root.bind_all("<MouseWheel>", self._on_mousewheel))
        container.bind("<Leave>", lambda e: self.root.unbind_all("<MouseWheel>"))

        self.root.after(300, self.load_calendar)

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def _set_status(self, text):
        self.root.after(0, lambda t=text: self.status.config(text=t))

    def load_calendar(self):
        try:
            start = datetime.strptime(self.date_entry.get().strip(), "%Y-%m-%d").date()
        except ValueError:
            messagebox.showerror("Error", "Enter the start date as YYYY-MM-DD")
            return
        end = add_one_month(start)
        include_value = self.value_var.get()
        self.load_btn.config(state=tk.DISABLED, text="Loading...")
        threading.Thread(target=self._fetch_all, args=(start, end, include_value),
                         daemon=True).start()

    def _fetch_all(self, start, end, include_value):
        try:
            watchlist = load_watchlist()
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror(
                "Error", f"Could not load watchlist: {e}"))
            self.root.after(0, self._reset_btn)
            return

        try:
            sp500_all = update_sp500_csv()
            nasdaq100 = update_nasdaq100_csv()
        except Exception as e:
            self.root.after(0, lambda err=e: messagebox.showwarning(
                "Index lists", f"Could not load index constituents: {err}"))
            sp500_all, nasdaq100 = [], []

        value_results = {}
        if include_value:
            value_results = load_cached_scan()
            if value_results is None:
                self._set_status("Scanning S&P 500 for stocks near 52w / multi-yr lows "
                                 "(downloading 5y prices, may take a minute)...")
                try:
                    value_results = scan_value_buys(sp500_all)
                    save_cached_scan(value_results)
                except Exception as e:
                    self.root.after(0, lambda err=e: messagebox.showwarning(
                        "Value scan failed", f"Could not scan S&P 500: {err}"))
                    value_results = {}

        must_watch = set(watchlist) & set(sp500_all) & set(nasdaq100)

        tags = {}
        for t in watchlist:
            tags.setdefault(t, set()).add("watchlist")
        for t in nasdaq100:
            tags.setdefault(t, set()).add("nasdaq 100")
        for t in value_results:
            tags.setdefault(t, set()).add("value buy")
        for t in must_watch:
            tags.setdefault(t, set()).add("must watch")

        cache = _load_earnings_cache()
        today = date.today()
        to_fetch = [t for t in tags if not _cache_entry_valid(cache.get(t), today)]
        n_cached = len(tags) - len(to_fetch)

        done = 0
        total = len(to_fetch)
        if total:
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
                futures = [pool.submit(earnings_dates_upcoming, t) for t in to_fetch]
                for fut in as_completed(futures):
                    ticker, dates = fut.result()
                    cache[ticker] = {"fetched": today.isoformat(),
                                     "dates": [d.isoformat() for d in dates]}
                    done += 1
                    self._set_status(f"Fetching earnings dates... {done}/{total} "
                                     f"({n_cached} from cache)")
            _save_earnings_cache(cache)

        events = {}
        for t, t_tags in tags.items():
            for ds in cache.get(t, {}).get("dates", []):
                d = date.fromisoformat(ds)
                if start <= d <= end:
                    events.setdefault(d, {}).setdefault(t, set()).update(t_tags)

        n_events = sum(len(day) for day in events.values())
        n_value = sum(1 for day in events.values()
                      for tg in day.values() if "value buy" in tg)
        n_ndaq = sum(1 for day in events.values()
                     for tg in day.values() if "nasdaq 100" in tg)
        n_must = sum(1 for day in events.values()
                     for tg in day.values() if "must watch" in tg)
        rng = f"{start.strftime('%b %d, %Y')} – {end.strftime('%b %d, %Y')}"
        parts = [f"{n_must} must watch", f"{n_ndaq} nasdaq 100"]
        if include_value:
            parts.append(f"{n_value} value buy · {len(value_results)} S&P 500 near lows")
        summary = f"{rng}: {n_events} earnings events ({' · '.join(parts)})"
        self.root.after(0, self._render_calendar, start, end, events)
        self.root.after(0, lambda s=summary: self.status.config(text=s))
        self.root.after(0, self._reset_btn)

    def _reset_btn(self):
        self.load_btn.config(state=tk.NORMAL, text="Load Calendar")

    def _render_calendar(self, start, end, events):
        for w in self.grid_frame.winfo_children():
            w.destroy()
        for c in range(7):
            self.grid_frame.columnconfigure(c, weight=1, uniform="day")

        for c, name in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]):
            tk.Label(self.grid_frame, text=name, font=("Segoe UI", 10, "bold"),
                     fg=MUTED, bg=BG).grid(row=0, column=c, sticky="ew", padx=2, pady=(2, 4))

        first = start - timedelta(days=start.weekday())
        last = end + timedelta(days=(6 - end.weekday()))
        today = date.today()

        d = first
        row = 1
        while d <= last:
            for col in range(7):
                in_range = start <= d <= end
                is_today = d == today
                cell = tk.Frame(self.grid_frame, bg=PANEL if in_range else BG,
                                highlightbackground="#2d7aff" if is_today else BORDER,
                                highlightthickness=2 if is_today else 1, width=165)
                cell.grid(row=row, column=col, sticky="new", padx=2, pady=2)

                tk.Label(cell, text=f"{d.strftime('%b')} {d.day}",
                         font=("Segoe UI", 9, "bold"),
                         fg=FG if in_range else "#484f58",
                         bg=PANEL if in_range else BG, anchor="w")\
                    .pack(fill=tk.X, padx=4, pady=(2, 1))

                if in_range:
                    for ticker in sorted(events.get(d, {})):
                        tgs = events[d][ticker]
                        if "must watch" in tgs:
                            bg_, fg_ = MUST_BG, MUST_FG
                        elif "value buy" in tgs:
                            bg_, fg_ = VALUE_BG, VALUE_FG
                        elif "watchlist" in tgs:
                            bg_, fg_ = WATCHLIST_BG, WATCHLIST_FG
                        else:
                            bg_, fg_ = NDAQ_BG, NDAQ_FG
                        extra = sorted(tgs - {"watchlist"})
                        text = f"{ticker} ({' · '.join(extra)})" if extra else ticker
                        tk.Button(cell, text=text, font=("Segoe UI", 8, "bold"),
                                  bg=bg_, fg=fg_,
                                  activebackground="#30363d", relief=tk.FLAT, cursor="hand2",
                                  command=lambda t=ticker: open_in_window(t))\
                            .pack(fill=tk.X, padx=3, pady=1)
                d += timedelta(days=1)
            row += 1


if __name__ == "__main__":
    root = tk.Tk()
    app = EarningsCalendarApp(root)
    root.mainloop()
