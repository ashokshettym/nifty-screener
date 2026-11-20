"""Promoter / FII / DII holding from Screener.in (best effort HTML parse; may break if the site changes).
Use sparingly (one stock at a time) and respect Screener's terms of use."""
import re, requests, pandas as pd
from io import StringIO
H = {"User-Agent": "Mozilla/5.0"}

def shareholding(sym):
    for suffix in ("consolidated/", ""):
        try:
            r = requests.get(f"https://www.screener.in/company/{sym.replace('&','%26')}/{suffix}", headers=H, timeout=15)
            m = re.search(r'id="shareholding".*?</section>', r.text, re.S) if r.status_code == 200 else None
            if not m: continue
            t = pd.read_html(StringIO(m.group(0)))[0]
            t = t.rename(columns={t.columns[0]: "Holder"})
            t["Holder"] = t.Holder.astype(str).str.replace(r"[\s+]+$", "", regex=True)
            return t.set_index("Holder").iloc[:, -6:]
        except Exception:
            continue
    return None

def summary(t):
    out = {}
    for k in ("Promoters", "FIIs", "DIIs"):
        if k in t.index:
            v = pd.to_numeric(t.loc[k].astype(str).str.rstrip("%"), errors="coerce").dropna()
            if len(v) >= 2: out[k] = (v.iloc[-1], round(v.iloc[-1]-v.iloc[-2], 2))
    return out
