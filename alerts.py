import os, smtplib, json, pathlib
from email.message import EmailMessage
from datetime import date
import pandas as pd, store

SENT = pathlib.Path(__file__).parent / "data" / "sent.json"
ok = lambda x: x is not None and x == x and x > 0

def cfg():
    s = {}
    try:
        import streamlit as st; s = dict(st.secrets["email"])
    except Exception: pass
    for k in ("host", "port", "user", "password", "to"): s.setdefault(k, os.getenv("ALERT_"+k.upper()))
    return s

def send(subject, body):
    c = cfg()
    if not (c.get("user") and c.get("password") and c.get("to")): return "Email not configured (see README)."
    try:
        m = EmailMessage(); m["Subject"], m["From"], m["To"] = subject, c["user"], c["to"]; m.set_content(body)
        with smtplib.SMTP(c.get("host") or "smtp.gmail.com", int(c.get("port") or 587)) as s:
            s.starttls(); s.login(c["user"], c["password"]); s.send_message(m)
        return "Email sent."
    except Exception as e: return f"Email failed: {e}"

def evaluate(df):
    s = store.load(); msgs = []
    wl = {x["Symbol"]: x for x in s["watchlist"] if x.get("Symbol")}
    pf = {x["Symbol"]: x for x in s["portfolio"] if x.get("Symbol")}
    for _, r in df[df.Symbol.isin(set(wl) | set(pf))].iterrows():
        k, w = r.Symbol, wl.get(r.Symbol, {})
        if ok(w.get("Alert Above")) and r.Price >= w["Alert Above"]: msgs.append(f"{k}: price ₹{r.Price} is above your alert ₹{w['Alert Above']}")
        if ok(w.get("Alert Below")) and r.Price <= w["Alert Below"]: msgs.append(f"{k}: price ₹{r.Price} is below your alert ₹{w['Alert Below']}")
        if k in wl and r.Signal == "Buy": msgs.append(f"{k}: Buy signal (score {r.Score}). Buy zone ₹{r['Buy At']}, stop ₹{r['Stop Loss']}, target ₹{r['Target 1']}")
        if k in pf:
            if r.Price <= r["Stop Loss"]: msgs.append(f"{k}: HOLDING hit stop-loss level ₹{r['Stop Loss']} (price ₹{r.Price})")
            if r.Price >= r["Target 1"]: msgs.append(f"{k}: HOLDING reached Target 1 ₹{r['Target 1']} (price ₹{r.Price})")
            if r.RSI > 75: msgs.append(f"{k}: HOLDING is overbought (RSI {int(r.RSI)})")
        d = r.get("Days to Result")
        if pd.notna(d) and 0 <= d <= 7: msgs.append(f"{k}: quarterly results in {int(d)} day(s) ({r['Next Result']})")
    return msgs

def check_and_send(df):
    msgs = evaluate(df); today = str(date.today())
    try: sent = json.loads(SENT.read_text())
    except Exception: sent = []
    new = [m for m in msgs if f"{today}|{m}" not in sent]
    if not new: return "No new alerts."
    res = send(f"Stock alerts ({len(new)})", "\n".join(new))
    if res == "Email sent.": SENT.write_text(json.dumps(sent[-300:] + [f"{today}|{m}" for m in new]))
    return f"{len(new)} new alert(s). {res}"
