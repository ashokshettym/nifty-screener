"""Price-only backtest of the momentum part of the score (fundamentals have no free point-in-time history).
Signals use data up to day t and trade from t+1 (no look-ahead). Uses TODAY's Nifty 50 list -> survivorship bias."""
import numpy as np, pandas as pd, yfinance as yf

def stats(eq):
    out = {}
    for c in eq:
        r = eq[c].pct_change().dropna(); yrs = max(len(r)/252, 0.01)
        out[c] = {"Total return %": eq[c].iloc[-1]-100, "CAGR %": ((eq[c].iloc[-1]/100)**(1/yrs)-1)*100,
                  "Volatility %": r.std()*252**.5*100, "Sharpe": r.mean()/r.std()*252**.5 if r.std() else 0,
                  "Max drawdown %": (eq[c]/eq[c].cummax()-1).min()*100}
    return pd.DataFrame(out).round(2)

def simulate(px, bm, top_n=10, rebalance=21, cost=0.002, regime=True):
    ret = px.pct_change()
    score = px.pct_change(63)*0.5 + px.pct_change(21)*0.2 + (px/px.rolling(200).mean()-1)*0.3
    score = score.where(px > px.rolling(50).mean())            # only stocks above 50-DMA
    if regime:                                                 # market filter: cash when Nifty < 200-DMA
        ok = (bm > bm.rolling(200).mean()).reindex(px.index).ffill().fillna(False).astype(bool)
        score.loc[~ok] = np.nan
    w = pd.DataFrame(np.nan, index=px.index, columns=px.columns)
    for d in px.index[200::rebalance]:
        top = score.loc[d].dropna().nlargest(top_n).index
        w.loc[d] = 0.0
        if len(top): w.loc[d, top] = 1/len(top)               # no candidates -> cash
    w = w.ffill().fillna(0.0)
    turn = w.diff().abs().sum(axis=1).fillna(0)
    strat = (w.shift(1)*ret).sum(axis=1) - turn*cost          # cost per unit traded (0.2% default)
    s = strat.loc[px.index[200]:]; b = bm.pct_change().reindex(s.index).fillna(0)
    eq = pd.DataFrame({"Strategy": (1+s).cumprod()*100, "Nifty 50": (1+b).cumprod()*100})
    return eq, w, stats(eq)

def run(symbols, years=3, **kw):
    raw = yf.download([s+".NS" for s in symbols]+["^NSEI"], period=f"{years+2}y", auto_adjust=True, progress=False)["Close"]
    bm = raw.pop("^NSEI").ffill()
    px = raw.rename(columns=lambda c: c[:-3]).dropna(axis=1, thresh=int(len(raw)*0.85)).ffill()
    return simulate(px, bm, **kw)
