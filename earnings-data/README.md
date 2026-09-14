# Earnings Gap Analyzer

A small desktop toolkit for exploring upcoming company earnings and inspecting earnings gaps (pre-close → post-open move) using `yfinance`.

Two entry points:
- Main analyzer: `earnings_app.py` — enter a ticker and run the gap analysis (table, charts, and stats).
- Calendar scanner: `earnings_calendar.py` — scan a watchlist and index constituents for upcoming earnings across a date range and jump to the analyzer for any ticker.

Quick start (Windows):

```powershell
cd earnings-data
.\run_app.bat        # creates .venv, installs deps, and runs the Earnings Gap Analyzer
.\run_calendar.bat   # creates .venv, installs deps, and runs the Earnings Calendar
```

Dependencies
- See `requirements.txt` for the primary runtime packages (`pandas`, `matplotlib`, `yfinance`, etc.).
- The calendar app uses `requests` (for fetching index lists) and performs heavier downloads; install missing packages with:

```powershell
.\venv\Scripts\python.exe -m pip install requests
```

If you prefer a nicer date picker, install `tkcalendar` (optional):

```powershell
.\venv\Scripts\python.exe -m pip install tkcalendar
```

Files and features
- `earnings_app.py` (main analyzer)
	- Enter a ticker (e.g. `NVDA`) and click **Run Analysis**.
	- Fetches the company's upcoming earnings dates via `yfinance`, calculates pre-close → post-open gap percentages, shows a table of events, a bar chart of gaps, a price chart with earnings markers, and summary stats.
	- `open_in_window(ticker)` can be used by other modules (the calendar) to open a focused analyzer window for a ticker.

- `earnings_calendar.py` (calendar scanner)
	- Scan modes: watchlist (`data/SPMO.csv`), S&P 500, and Nasdaq-100 constituents.
	- Automatic weekly refresh of index CSVs (fetched from Wikipedia when a local file is older than 7 days).
	- Optional S&P 500 "value scan" that checks 5y prices for stocks trading near their 52-week or multi-year lows (configurable threshold), cached daily in `value_scan_cache.json`.
	- Earnings date results are cached in `earnings_cache.json` to reduce repeated yfinance calls (cache entries are reused for up to 7 days when still valid).
	- Click a ticker button in the calendar to open the Earnings Gap Analyzer window for that ticker (analyzer opens in a new window and starts analysis automatically).

Run the calendar directly:

```powershell
cd earnings-data
.\run_calendar.bat  # optional argument: number of days to show (e.g. run_calendar.bat 60)
```

Data files
- `data/SPMO.csv` — your personal watchlist (one CSV column named `Ticker` or the first column used as tickers).
- `data/SNP500.csv`, `data/NASDAQ100.csv` — cached index constituents (auto-refreshed weekly from Wikipedia when missing or stale).

Cache files (created in `earnings-data`):
- `value_scan_cache.json` — caches daily S&P 500 value-scan results.
- `earnings_cache.json` — caches recently fetched earnings dates per ticker.

Notes & troubleshooting
- The calendar is designed as a standalone window (launchable via `run_calendar.bat`) and also provides functions to open the analyzer window for a ticker.
- If GUI components fail to appear, ensure you have a desktop session available (Tkinter requires a graphical environment).
- If you see import errors for packages such as `requests` or `tkcalendar`, install them into the `.venv` created by the batch scripts:

```powershell
cd earnings-data
.\.venv\Scripts\python.exe -m pip install requests tkcalendar
```

- If you want the calendar to be modal inside the main app (block interaction until closed), that behavior can be added — currently the calendar runs as a separate window and opens analyzer windows via `open_in_window()`.

How to add or edit your watchlist
- Place a CSV at `data/SPMO.csv` with either a `Ticker` column or the tickers in the first column. Tickers should be plain symbols (e.g. `AAPL`, `MSFT`, `NVDA`).

If you'd like, I can:
- Add `requests` and `tkcalendar` to `requirements.txt` and re-run the installer.
- Convert the calendar behavior into an in-app modal dialog that blocks the main window (your earlier preference).

Enjoy — tell me if you want the modal dialog behavior or additional export/ICS integration.
