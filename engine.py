"""Data + scoring engine. Live data from Yahoo Finance (free, ~15 min delayed for NSE)."""
import numpy as np, pandas as pd, yfinance as yf
from datetime import date
import requests, pathlib, time, sentiment
from concurrent.futures import ThreadPoolExecutor

# Edit this list when NSE changes Nifty 50 constituents (or after demergers/renames).
NIFTY50 = ["ADANIENT","ADANIPORTS","APOLLOHOSP","ASIANPAINT","AXISBANK","BAJAJ-AUTO","BAJFINANCE","BAJAJFINSV",
"BEL","BHARTIARTL","CIPLA","COALINDIA","DRREDDY","EICHERMOT","ETERNAL","GRASIM","HCLTECH","HDFCBANK","HDFCLIFE",
"HEROMOTOCO","HINDALCO","HINDUNILVR","ICICIBANK","INDUSINDBK","INFY","ITC","JSWSTEEL","JIOFIN","KOTAKBANK","LT",
"M&M","MARUTI","NESTLEIND","NTPC","ONGC","POWERGRID","RELIANCE","SBILIFE","SBIN","SHRIRAMFIN","SUNPHARMA",
"TATACONSUM","TATAMOTORS","TATASTEEL","TCS","TECHM","TITAN","TRENT","ULTRACEMCO","WIPRO"]

ORDER_KW = ("order","contract","bags","bagged","wins","awarded","letter of award","loa","deal")
POS_KW = ("profit rises","profit jumps","record","beats","upgrade","surge","strong","growth","bags","wins")
NEG_KW = ("falls","slump","downgrade","probe","penalty","loss","miss","fraud","cuts")

def rsi(c, n=14):
    d = c.diff(); up = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    return float(100 - 100/(1 + up.iloc[-1]/max(dn.iloc[-1], 1e-9)))

def atr(h, n=14):
    tr = pd.concat([h.High-h.Low, (h.High-h.Close.shift()).abs(), (h.Low-h.Close.shift()).abs()], axis=1).max(axis=1)
    return float(tr.rolling(n).mean().iloc[-1])

def scale(x, lo, hi):
    """Linear map to 0-100 (lo->0, hi->100). Works inverted if lo>hi. None -> None."""
    if x is None or (isinstance(x, float) and np.isnan(x)): return None
    return float(np.clip((x-lo)/(hi-lo), 0, 1)*100)

def avg(xs):
    xs = [x for x in xs if x is not None]
    return float(np.mean(xs)) if xs else 50.0

def get_news(t):
    out = []
    try:
        for n in (t.news or [])[:15]:
            c = n.get("content", n)
            title = c.get("title", "")
            link = (c.get("canonicalUrl") or {}).get("url") or c.get("link", "")
            low = title.lower()
            out.append({"title": title, "link": link, "date": c.get("pubDate", ""),
                        "order": any(k in low for k in ORDER_KW),
                        "tone": 1 if any(k in low for k in POS_KW) else (-1 if any(k in low for k in NEG_KW) else 0)})
    except Exception:
        pass
    return out

def next_result(t):
    try:
        d = t.calendar.get("Earnings Date")
        d = sorted(x for x in d if x >= date.today())
        return str(d[0]) if d else None
    except Exception:
        return None

def score(df, wm=40, wf=40, wo=20, regime_ok=True):
    df = df.copy(); tot = (wm + wf + wo) or 1
    df["Score"] = ((df.Momentum*wm + df.Fundamental*wf + df.Orders*wo)/tot).round().astype(int)
    df["Signal"] = pd.cut(df.Score, [-1, 49, 69, 100], labels=["Avoid", "Watch", "Buy"]).astype(str)
    if not regime_ok: df.loc[df.Signal == "Buy", "Signal"] = "Watch"   # market filter
    df["Days to Result"] = (pd.to_datetime(df["Next Result"]) - pd.Timestamp.today().normalize()).dt.days
    return df

def analyze(sym):
    try:
        t = yf.Ticker(sym + ".NS")
        h = t.history(period="1y", auto_adjust=True).dropna(subset=["Close", "High", "Low"])
        if len(h) < 60: return None
        info = t.info or {}
        c = h.Close; p = float(c.iloc[-1])
        ret = lambda d: (p/float(c.iloc[-d-1])-1)*100 if len(c) > d else np.nan
        sma20, sma50 = float(c.rolling(20).mean().iloc[-1]), float(c.rolling(50).mean().iloc[-1])
        sma200 = float(c.rolling(200).mean().iloc[-1]) if len(c) >= 200 else np.nan
        a, r = atr(h), rsi(c)
        hi52, lo52 = float(h.High.max()), float(h.Low.min())
        volx = float(h.Volume.iloc[-1] / max(h.Volume.tail(20).mean(), 1))
        news = get_news(t); nres = next_result(t)
        news = sentiment.annotate(news); orders = sum(n["order"] for n in news); tone = sentiment.aggregate(news)

        # ---- trade levels (rule based, ATR driven) ----
        buy = round(min(p, max(sma20, p - 0.5*a)), 2)      # limit near short-term support
        stop = round(buy - 2*a, 2)                          # 2 x ATR below entry
        target = round(buy + 3*a, 2)                        # 1.5 : 1 reward / risk
        target2 = round(buy + 5*a, 2)
        if not np.isfinite(buy + stop + target + target2): return None   # skip stocks with bad data

        de = info.get("debtToEquity"); de = de/100 if de is not None else None   # Yahoo gives %
        pe, pb = info.get("trailingPE"), info.get("priceToBook")
        roe = (info.get("returnOnEquity") or np.nan)*100
        margin = (info.get("profitMargins") or np.nan)*100
        eg = (info.get("earningsGrowth") or np.nan)*100
        rg = (info.get("revenueGrowth") or np.nan)*100
        dy = (info.get("dividendRate") or 0)/p*100

        # ---- scores (0-100) ----
        trend_up = p > sma50 > (sma200 if not np.isnan(sma200) else 0)
        mom = avg([scale(ret(63), -5, 25), scale(ret(21), -5, 12), scale(100-abs(r-62)*3, 0, 100),
                   100 if trend_up else (50 if p > sma50 else 0), scale(volx, 0.7, 1.8),
                   scale((p/hi52-1)*100, -25, 0)])
        fund = avg([scale(pe, 45, 12) if pe and pe > 0 else 25, scale(pb, 8, 1), scale(de, 1.5, 0),
                    scale(roe, 5, 22), scale(margin, 3, 20), scale(eg, -10, 25), scale(rg, 0, 18)])
        order = min(orders*25, 100)*0.7 + avg([scale(tone, -0.5, 0.5)])*0.3
        return dict(Symbol=sym, Name=info.get("shortName", sym), Sector=info.get("sector", "-"), Price=round(p, 2),
            **{"Day %": round(ret(1), 2), "1M %": round(ret(21), 1), "3M %": round(ret(63), 1), "6M %": round(ret(126), 1)},
            RSI=round(r, 0), **{"Vol x": round(volx, 2), "Above 200DMA": bool(p > sma200) if not np.isnan(sma200) else None,
            "52W High": round(hi52, 2), "52W Low": round(lo52, 2), "From High %": round((p/hi52-1)*100, 1),
            "Buy At": buy, "Stop Loss": stop, "Target 1": target, "Target 2": target2,
            "Risk:Reward": round((target-buy)/max(buy-stop, 0.01), 2),
            "Analyst Target": info.get("targetMeanPrice"), "Analyst View": info.get("recommendationKey", "-"),
            "PE": pe and round(pe, 1), "PB": pb and round(pb, 2), "Debt/Equity": de and round(de, 2),
            "Debt Free": bool(de is not None and de < 0.05), "ROE %": round(roe, 1), "Net Margin %": round(margin, 1),
            "Profit Growth %": round(eg, 1), "Revenue Growth %": round(rg, 1), "Div Yield %": round(dy, 2),
            "Mkt Cap (Cr)": round((info.get("marketCap") or 0)/1e7), "Order News": orders, "Next Result": nres, "News Tone": round(tone, 2),
            "Momentum": round(mom), "Fundamental": round(fund), "Orders": round(order)}, _news=news)
    except Exception as e:
        print("failed", sym, e); return None

URLS = {"Nifty 50": "https://archives.nseindia.com/content/indices/ind_nifty50list.csv",
        "Nifty 200": "https://archives.nseindia.com/content/indices/ind_nifty200list.csv"}

def get_universe(name):
    """Constituents from NSE (cached to data/), falling back to the cached file, then the built-in Nifty 50 list."""
    p = pathlib.Path(__file__).parent / "data" / (name.replace(" ", "") + ".csv"); p.parent.mkdir(exist_ok=True)
    src = "NSE (live)"
    try:
        r = requests.get(URLS[name], headers={"User-Agent": "Mozilla/5.0"}, timeout=20); r.raise_for_status(); p.write_text(r.text)
    except Exception:
        src = "cached file"
    try: return pd.read_csv(p)["Symbol"].dropna().astype(str).str.strip().tolist(), src
    except Exception: return NIFTY50, "built-in Nifty 50 (could not reach NSE)"

def market_regime():
    try:
        h = yf.Ticker("^NSEI").history(period="2y")["Close"].dropna()
        p, s200 = float(h.iloc[-1]), float(h.rolling(200).mean().iloc[-1])
        return dict(price=round(p), sma200=round(s200), bullish=p > s200)
    except Exception:
        return dict(price=None, sma200=None, bullish=True)

def sector_table(df):
    d = df.assign(_a=df["Above 200DMA"].map(lambda x: float(x) if x is not None and x == x else np.nan))
    g = d.groupby("Sector").agg(Stocks=("Symbol", "count"), **{"Avg 1M %": ("1M %", "mean"), "Avg 3M %": ("3M %", "mean"),
        "Avg 6M %": ("6M %", "mean"), "Above 200DMA %": ("_a", "mean"), "Avg Score": ("Score", "mean")})
    g["Above 200DMA %"] *= 100
    g["Strength"] = (g["Avg 3M %"].rank(pct=True)*0.4 + g["Avg 1M %"].rank(pct=True)*0.2 + g["Above 200DMA %"].rank(pct=True)*0.4)*100
    g["Rank"] = g.Strength.rank(ascending=False, method="min").astype(int)
    return g.sort_values("Rank").round(1)

def sector_history(sym_sector, period="1y"):
    """Equal-weighted sector indices (rebased to 100) vs Nifty 50, plus per-stock rebased prices."""
    syms = list(sym_sector)
    raw = yf.download([x + ".NS" for x in syms] + ["^NSEI"], period=period, auto_adjust=True, progress=False)["Close"]
    bm = raw.pop("^NSEI").ffill()
    px = raw.rename(columns=lambda c: c[:-3]).ffill().dropna(axis=1, how="all")
    rb = px / px.bfill().iloc[0] * 100
    idx = rb.T.groupby(pd.Series(sym_sector)).mean().T
    idx["Nifty 50"] = bm / bm.dropna().iloc[0] * 100
    return idx, rb

def load_all(universe="Nifty 50"):
    syms, src = get_universe(universe); rows = []
    for i in range(0, len(syms), 25):                       # batches keep Yahoo from rate-limiting us
        with ThreadPoolExecutor(6) as ex: rows += [r for r in ex.map(analyze, syms[i:i+25]) if r]
        if len(syms) > 60: time.sleep(1.5)
    return rows, src

def history(sym, period="1y"):
    return yf.Ticker(sym + ".NS").history(period=period, auto_adjust=True)
