# Earnings Gap Analyzer

Run the desktop Tkinter app that analyzes earnings gaps using `yfinance`.

Quick start (Windows):

```powershell
cd earnings-data
.\run_app.bat
```

This will create a `.venv` virtual environment, install dependencies from `requirements.txt`, and run `earnings_app.py`.

## Earnings Calendar

`earnings_calendar.py` shows upcoming earnings for the watchlist in `data/SPMO.csv` over the 1 month starting at a selected date. It can also scan all S&P 500 stocks for ones trading near their 52-week or multi-year lows (within 5%) and tags their earnings dates on the calendar as "value buy" — gold buttons are value buys, blue buttons are watchlist tickers. The S&P 500 constituent list lives in `data/SNP500.csv` and is refreshed automatically once a week (when the file is older than 7 days it is re-fetched from Wikipedia; if the refresh fails, the stale file is used). The scan result is cached for the day in `value_scan_cache.json`. Upcoming earnings dates per ticker are cached in `earnings_cache.json` — reused the same day, and up to 7 days while the next earnings date is already known — so repeat loads and date-range changes only fetch tickers whose data went stale.

```powershell
cd earnings-data
.\run_calendar.bat
```

Enter a start date (`YYYY-MM-DD`, defaults to today) and click **Load Calendar**. Clicking any ticker button opens the Earnings Gap Analyzer window for that ticker and runs the analysis automatically.
