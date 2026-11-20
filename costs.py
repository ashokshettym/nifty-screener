"""Estimated delivery-equity charges and capital-gains tax (India). Defaults checked Nov 2026; verify before relying on them."""
import pandas as pd

def charges(v, side, c):
    brok = v*c["brokerage_pct"]/100; exch = v*0.0000297; sebi = v*0.000001
    return (brok + v*0.001 + exch + sebi + (v*0.00015 if side == "buy" else 0)
            + 0.18*(brok + exch + sebi) + (c["dp_charge"] if side == "sell" else 0))   # STT 0.1% each side

def apply(m, c):
    m = m.copy()
    m["Invested"] = m.Qty*m.Avg; m["Value"] = m.Qty*m.Price; m["P/L"] = m.Value - m.Invested; m["P/L %"] = m["P/L"]/m.Invested*100
    m["Charges"] = [charges(i, "buy", c) + charges(v, "sell", c) for i, v in zip(m.Invested, m.Value)]
    m["Held Days"] = (pd.Timestamp.today().normalize() - pd.to_datetime(m["Buy Date"])).dt.days
    m["Net Pre-tax"] = m["P/L"] - m.Charges
    lt = m["Held Days"] > 365                                  # missing date counts as short-term
    stg = max(m.loc[~lt, "Net Pre-tax"].sum(), 0); ltg = max(m.loc[lt, "Net Pre-tax"].sum() - c["ltcg_exempt"], 0)
    tax = (stg*c["stcg"] + ltg*c["ltcg"])/100*(1 + c["cess"]/100)
    return m, dict(invested=m.Invested.sum(), value=m.Value.sum(), gross=m["P/L"].sum(), charges=m.Charges.sum(), tax=tax,
                   net=m["Net Pre-tax"].sum() - tax, missing=int(m["Buy Date"].isna().sum()))
