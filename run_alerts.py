"""Run on a schedule (Windows Task Scheduler / cron): python run_alerts.py"""
import engine, alerts, pandas as pd
rows, _ = engine.load_all("Nifty 50")
for r in rows: r.pop("_news", None)
print(alerts.check_and_send(engine.score(pd.DataFrame(rows), regime_ok=engine.market_regime()["bullish"])))
