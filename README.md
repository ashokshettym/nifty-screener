[README.md](https://github.com/user-attachments/files/35127757/README.md)
# Nifty 50 Momentum Screener
Run: double-click `run.bat` (or `pip install -r requirements.txt` then `streamlit run app.py`). Needs Python 3.10+ and internet.
Edit `NIFTY50` in engine.py when index constituents/tickers change (e.g. after demergers).
Buy/Stop/Target = pullback entry near 20-DMA, stop 2xATR below, targets 3x and 5xATR above. Educational only, not advice.

## New features
- Portfolio and watchlist: edit in the app, click Save (stored in data/state.json).
- Alerts: price above/below, Buy signal, holding hits stop/target/overbought, results within 7 days.
- Email: copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and fill in (Gmail needs an App Password).
- Automatic emails: Windows Task Scheduler, run daily after market close: `.venv\Scripts\python run_alerts.py`.
- Backtest: price-momentum only, monthly rebalance, 0.2% cost, no look-ahead. Survivorship bias exists.
- Shareholding: scraped from Screener.in on demand; may break if the site changes.

- FinBERT: `pip install -r requirements-finbert.txt`, then pick it at the top of the app (first run downloads a ~440 MB model; slower).
- Sectors tab: price history of sector indices vs Nifty 50, with drill-down to stocks.
