import pandas as pd, streamlit as st, plotly.graph_objects as go
from datetime import datetime
import engine, store, holdings, backtest, alerts, costs, sentiment

st.set_page_config(page_title="Nifty 50 Momentum Screener", layout="wide")

@st.cache_data(ttl=900, show_spinner="Fetching live Nifty 50 data...")
def load(universe, mode):
    sentiment.set_mode(mode)
    rows, src = engine.load_all(universe)
    news = {r["Symbol"]: r.pop("_news") for r in rows}
    return pd.DataFrame(rows), news, datetime.now().strftime("%d %b %Y %H:%M:%S"), src

universe = st.radio("Universe", ["Nifty 50", "Nifty 200"], horizontal=True, help="Nifty 200 loads in batches and can take a few minutes the first time.")
senti = st.radio("News sentiment", ["VADER (fast)", "FinBERT (more accurate, slower)"], horizontal=True)
mode = "finbert" if senti.startswith("FinBERT") else "vader"
if mode == "finbert" and not sentiment.finbert_available():
    st.warning("FinBERT is not installed. Run: pip install -r requirements-finbert.txt. Using VADER for now."); mode = "vader"
df, news, ts, src = load(universe, mode)
st.title("Nifty 50 Momentum & Fundamentals Screener")
st.caption(f"Data: Yahoo Finance (delayed ~15 min) · Loaded {ts} · List: {src} · Buy/sell levels are rule-based (ATR), not advice.")

with st.sidebar:
    if st.button("Refresh live data"): st.cache_data.clear(); st.rerun()
    cards = st.toggle("Card view (phone friendly)")
    use_mkt = st.checkbox("Market filter: no new Buys when Nifty is below its 200-DMA", True)
    st.subheader("Score weights")
    wm, wf, wo = (st.slider("Momentum", 0, 100, 40), st.slider("Fundamentals", 0, 100, 40), st.slider("Order wins / news", 0, 100, 20))
    st.subheader("Filters")
    sectors = st.multiselect("Sector", sorted(df.Sector.unique()))
    min_score = st.slider("Minimum score", 0, 90, 0)
    max_pe = st.number_input("Max PE (0 = off)", 0.0, 500.0, 0.0)
    max_pb = st.number_input("Max PB (0 = off)", 0.0, 100.0, 0.0)
    max_de = st.number_input("Max Debt/Equity (0 = off)", 0.0, 10.0, 0.0)
    min_roe = st.number_input("Min ROE %", -50.0, 100.0, 0.0)
    debt_free = st.checkbox("Debt free only")
    uptrend = st.checkbox("Above 200-DMA only")
    min_rr = st.number_input("Min risk:reward", 0.0, 5.0, 0.0)

t = (wm + wf + wo) or 1
@st.cache_data(ttl=900)
def mkt(): return engine.market_regime()
mk = mkt()
df = engine.score(df, wm, wf, wo, regime_ok=(mk["bullish"] or not use_mkt))
df["Sector Rank"] = df.Sector.map(engine.sector_table(df)["Rank"])
if mk["price"]:
    msg = f"Nifty 50 index {mk['price']:,} vs 200-DMA {mk['sma200']:,}: " + ("uptrend, new Buy signals allowed." if mk["bullish"] else ("downtrend. New Buy signals are shown as Watch." if use_mkt else "downtrend (market filter is off)."))
    (st.success if mk["bullish"] else st.warning)(msg)
f = df[df.Score >= min_score]
if sectors: f = f[f.Sector.isin(sectors)]
if max_pe: f = f[f.PE.notna() & (f.PE <= max_pe)]
if max_pb: f = f[f.PB.notna() & (f.PB <= max_pb)]
if max_de: f = f[f["Debt/Equity"].notna() & (f["Debt/Equity"] <= max_de)]
if min_roe: f = f[f["ROE %"] >= min_roe]
if debt_free: f = f[f["Debt Free"]]
if uptrend: f = f[f["Above 200DMA"] == True]
if min_rr: f = f[f["Risk:Reward"] >= min_rr]
f = f.sort_values("Score", ascending=False)

c = st.columns(4)
c[0].metric("Stocks shown", len(f)); c[1].metric("Buy", int((f.Signal == "Buy").sum()))
c[2].metric("Watch", int((f.Signal == "Watch").sum())); c[3].metric("Avoid", int((f.Signal == "Avoid").sum()))

g = lambda v: "-" if pd.isna(v) else v
def render_cards(d):
    st.markdown("<style>.block-container{padding:1rem .6rem}</style>", unsafe_allow_html=True)
    for _, x in d.head(40).iterrows():
        with st.container(border=True):
            l, rt = st.columns([3, 2])
            l.markdown(f"**{x.Symbol}** · {x.Sector} (sector rank {g(x['Sector Rank'])})  \n₹{x.Price} ({x['Day %']:+.1f}%) · 3M {x['3M %']:+.1f}% · RSI {g(x.RSI)}")
            rt.markdown(f"**{x.Signal}** · Score {x.Score}")
            st.markdown(f"Buy ₹{x['Buy At']} · Stop ₹{x['Stop Loss']} · T1 ₹{x['Target 1']} · T2 ₹{x['Target 2']} · R:R {x['Risk:Reward']}  \nPE {g(x.PE)} · PB {g(x.PB)} · D/E {g(x['Debt/Equity'])} · ROE {g(x['ROE %'])}% · Orders in news {x['Order News']}")
tab1, tab2, tab3, tabS, tabP, tabB, tabA = st.tabs(["Screener", "Stock detail", "Fundamentals", "Sectors", "Portfolio & watchlist", "Backtest", "Alerts & results"])
trade_cols = ["Symbol","Name","Sector","Price","Day %","3M %","RSI","Score","Signal","Buy At","Stop Loss","Target 1","Target 2","Risk:Reward","Order News"]
fund_cols = ["Symbol","Sector","Price","PE","PB","Debt/Equity","Debt Free","ROE %","Net Margin %","Profit Growth %","Revenue Growth %","Div Yield %","Mkt Cap (Cr)","Analyst Target","Analyst View"]

def colour(v):
    return "color:#0f7b53" if isinstance(v, (int, float)) and v > 0 else ("color:#b3261e" if isinstance(v, (int, float)) and v < 0 else "")

with tab1:
    if cards: render_cards(f)
    else: st.dataframe(f[trade_cols].style.map(colour, subset=["Day %", "3M %"]), use_container_width=True, hide_index=True, height=560,
                 column_config={"Score": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%d")})
    st.download_button("Download CSV", f.to_csv(index=False), "nifty50_screen.csv")
with tab3:
    st.dataframe(f[fund_cols], use_container_width=True, hide_index=True, height=560)

with tab2:
    if f.empty: st.info("No stocks match the filters.")
    else:
        sym = st.selectbox("Stock", f.Symbol.tolist())
        r = df[df.Symbol == sym].iloc[0]
        st.subheader(f"{r.Name} ({sym}) · {r.Sector} · {r.Signal} · Score {r.Score}")
        m = st.columns(5)
        m[0].metric("Price", f"₹{r.Price}", f"{r['Day %']}%"); m[1].metric("Buy at", f"₹{r['Buy At']}")
        m[2].metric("Stop loss", f"₹{r['Stop Loss']}"); m[3].metric("Target 1 / 2", f"₹{r['Target 1']} / {r['Target 2']}")
        m[4].metric("Risk:Reward", r["Risk:Reward"])
        h = engine.history(sym, "1y")
        fig = go.Figure(go.Candlestick(x=h.index, open=h.Open, high=h.High, low=h.Low, close=h.Close, name=sym))
        for n, w in (("SMA50", 50), ("SMA200", 200)): fig.add_scatter(x=h.index, y=h.Close.rolling(w).mean(), name=n)
        for lbl, y, col in (("Buy", r["Buy At"], "blue"), ("Stop", r["Stop Loss"], "red"), ("T1", r["Target 1"], "green"), ("T2", r["Target 2"], "darkgreen")):
            fig.add_hline(y=y, line_dash="dash", line_color=col, annotation_text=lbl)
        fig.update_layout(height=520, xaxis_rangeslider_visible=False, margin=dict(t=20))
        st.plotly_chart(fig, use_container_width=True)
        a, b = st.columns(2)
        a.markdown("**Valuation & quality**"); a.table(pd.DataFrame({"": ["PE","PB","Debt/Equity","Debt free","ROE %","Net margin %","Profit growth %","Revenue growth %","Dividend yield %","Mkt cap (Cr)","Analyst target","Analyst view","52W high / low"],
            "Value": [r.PE, r.PB, r["Debt/Equity"], "Yes" if r["Debt Free"] else "No", r["ROE %"], r["Net Margin %"], r["Profit Growth %"], r["Revenue Growth %"], r["Div Yield %"], r["Mkt Cap (Cr)"], r["Analyst Target"], r["Analyst View"], f"{r['52W High']} / {r['52W Low']}"]}).astype(str).set_index(""))
        b.markdown("**Momentum**"); b.table(pd.DataFrame({"": ["1M %","3M %","6M %","RSI","Volume vs 20d avg","Above 200-DMA","From 52W high %","Momentum / Fundamental / Orders score"],
            "Value": [r["1M %"], r["3M %"], r["6M %"], r.RSI, r["Vol x"], r["Above 200DMA"], r["From High %"], f"{r.Momentum} / {r.Fundamental} / {r.Orders}"]}).astype(str).set_index(""))
        st.markdown("**Latest news** (🟢 order/contract headline)")
        for n in news.get(sym, []): st.markdown(f"{'🟢' if n['order'] else '•'} [{n['title']}]({n['link']})")


with tab2:
    if not f.empty:
        st.divider(); st.markdown("**Position size calculator**")
        c1, c2 = st.columns(2)
        capital = c1.number_input("Capital (₹)", 0, value=500000, step=50000); risk = c2.number_input("Risk per trade (%)", 0.1, 5.0, 1.0)
        gap = r["Buy At"] - r["Stop Loss"]
        qty = int(capital*risk/100/max(gap, 0.01)) if pd.notna(gap) else 0
        st.write(f"Buy **{qty}** shares near ₹{r['Buy At']} (about ₹{qty*r['Buy At']:,.0f}). If the stop hits, you lose about ₹{capital*risk/100:,.0f}.")
        st.markdown("**Promoter / FII / DII holding**")
        if st.button("Load shareholding from Screener.in"):
            sh = holdings.shareholding(sym)
            if sh is None: st.warning("Could not read Screener.in right now (blocked or page changed).")
            else:
                for col, (k, (v, d)) in zip(st.columns(3), holdings.summary(sh).items()): col.metric(k, f"{v}%", f"{d} pts vs last quarter")
                st.dataframe(sh, use_container_width=True)

state = store.load()
with tabP:
    st.subheader("Portfolio")
    base = pd.DataFrame(state["portfolio"], columns=["Symbol", "Qty", "Avg", "Buy Date"]).astype({"Qty": float, "Avg": float})
    base["Buy Date"] = pd.to_datetime(base["Buy Date"], errors="coerce")
    pf = st.data_editor(base, num_rows="dynamic", use_container_width=True, key="pf2", column_config={
        "Symbol": st.column_config.SelectboxColumn(options=sorted(df.Symbol)), "Buy Date": st.column_config.DateColumn()})
    with st.expander("Brokerage & tax assumptions (edit to match your broker)"):
        k = st.columns(3); k2 = st.columns(3)
        cfg = dict(brokerage_pct=k[0].number_input("Brokerage % per side", 0.0, 1.0, 0.0, 0.01), dp_charge=k[1].number_input("DP charge per sell (₹)", 0.0, 100.0, 15.34),
                   cess=k[2].number_input("Cess %", 0.0, 10.0, 4.0), stcg=k2[0].number_input("STCG % (held 12 months or less)", 0.0, 50.0, 20.0),
                   ltcg=k2[1].number_input("LTCG %", 0.0, 50.0, 12.5), ltcg_exempt=k2[2].number_input("LTCG yearly exemption (₹)", 0.0, 1e7, 125000.0))
        st.caption("Includes STT 0.1% on buy and sell, exchange and SEBI fees, stamp duty on buy, GST and DP charge. Tax is an estimate if you sold everything today. It ignores loss set-off and other income.")
    m = pf.dropna(subset=["Symbol"]).merge(df[["Symbol", "Price", "Signal", "Stop Loss", "Target 1", "RSI"]], on="Symbol", how="left")
    if len(m):
        m, sm = costs.apply(m, cfg)
        q = st.columns(5)
        q[0].metric("Invested", f"₹{sm['invested']:,.0f}"); q[1].metric("Value", f"₹{sm['value']:,.0f}"); q[2].metric("Gross P/L", f"₹{sm['gross']:,.0f}")
        q[3].metric("Charges + est. tax", f"₹{sm['charges'] + sm['tax']:,.0f}"); q[4].metric("Net P/L if sold today", f"₹{sm['net']:,.0f}")
        if sm["missing"]: st.info(f"{sm['missing']} holding(s) have no Buy Date, so they are taxed as short-term. Add the dates for a better estimate.")
        st.dataframe(m[["Symbol", "Qty", "Avg", "Price", "Invested", "Value", "P/L", "P/L %", "Charges", "Held Days", "Signal", "Stop Loss", "Target 1"]].round(2), use_container_width=True, hide_index=True)
    st.subheader("Watchlist (optional alert prices)")
    wl = st.data_editor(pd.DataFrame(state["watchlist"], columns=["Symbol", "Alert Above", "Alert Below"]).astype({"Alert Above": float, "Alert Below": float}), num_rows="dynamic", use_container_width=True, key="wl",
                        column_config={"Symbol": st.column_config.SelectboxColumn(options=sorted(df.Symbol))})
    if st.button("Save portfolio & watchlist"):
        p2 = pf.dropna(subset=["Symbol"]).copy(); p2["Buy Date"] = p2["Buy Date"].dt.strftime("%Y-%m-%d")
        store.save({"portfolio": store.clean(p2), "watchlist": store.clean(wl.dropna(subset=["Symbol"]))}); st.success("Saved")
    st.caption("On Streamlit Cloud, saved data can reset when the app restarts. Download a backup below.")
    st.download_button("Download backup", __import__("json").dumps(state), "portfolio_backup.json")

with tabS:
    sec = engine.sector_table(df)
    st.caption("Strength = 3M return (40%), 1M return (20%) and share of stocks above their 200-DMA (40%), ranked across sectors. Rank 1 is strongest.")
    st.dataframe(sec, use_container_width=True)
    st.bar_chart(sec["Avg 3M %"])
    best = df.sort_values("Score", ascending=False).drop_duplicates("Sector")[["Sector", "Symbol", "Name", "Score", "Signal", "Price"]]
    st.markdown("**Top-scoring stock in each sector**"); st.dataframe(best.assign(Rank=best.Sector.map(sec["Rank"])).sort_values("Rank"), use_container_width=True, hide_index=True)

with tabB:
    st.caption("Tests the price-momentum part of the score only (no free historical fundamentals). Uses today's Nifty 50 list, so results look better than real life. Past results do not predict future returns.")
    b1, b2, b3 = st.columns(3)
    yrs = b1.slider("Years", 1, 5, 3); topn = b2.slider("Stocks held", 3, 20, 10); reb = b3.slider("Rebalance every (trading days)", 5, 63, 21)
    reg = st.checkbox("Hold cash when Nifty is below its 200-day average", True)
    if st.button("Run backtest"):
        with st.spinner("Downloading history and simulating..."): st.session_state["bt"] = backtest.run(df.Symbol.tolist(), yrs, top_n=topn, rebalance=reb, regime=reg)
    if "bt" in st.session_state:
        eq, w, bs = st.session_state["bt"]
        st.line_chart(eq); st.dataframe(bs, use_container_width=True)
        last = w.iloc[-1]; st.markdown("**Current picks by the backtest rules:** " + ", ".join(last[last > 0].index))
        st.caption("Includes 0.2% cost per trade. Taxes and slippage are not included.")

with tabA:
    st.subheader("Upcoming quarterly results (next 60 days)")
    res = df[df["Days to Result"].between(0, 60)].sort_values("Days to Result")[["Symbol", "Name", "Next Result", "Days to Result", "Signal", "Price"]]
    st.dataframe(res, use_container_width=True, hide_index=True)
    msgs = alerts.evaluate(df)
    st.subheader(f"Active alerts for your portfolio & watchlist ({len(msgs)})")
    for x in msgs: st.write("🔔 " + x)
    k1, k2 = st.columns(2)
    if k1.button("Email these alerts now"): st.info(alerts.check_and_send(df))
    if k2.button("Send test email"): st.info(alerts.send("Test alert", "Your stock alert email is working."))
    st.caption("For automatic emails, schedule run_alerts.py (see README).")


@st.cache_data(ttl=900, show_spinner="Downloading sector price history...")
def shist(pairs, period):
    return engine.sector_history(dict(pairs), period)

with tabS:
    st.divider(); st.subheader("Sector price history")
    p1, p2 = st.columns(2)
    per = p1.selectbox("Period", ["3mo", "6mo", "1y", "2y"], index=2)
    view = p2.radio("View", ["Rebased to 100", "Relative to Nifty 50"], horizontal=True)
    pick = st.multiselect("Sectors", list(sec.index), default=list(sec.index[:3]))
    if pick:
        sidx, srb = shist(tuple(df.set_index("Symbol").Sector.items()), per)
        cols = [c for c in pick if c in sidx.columns]
        if view == "Rebased to 100": st.line_chart(sidx[cols + ["Nifty 50"]])
        else: st.line_chart(sidx[cols].div(sidx["Nifty 50"], axis=0) * 100)
        st.caption("Equal-weighted average of the sector's stocks. In the relative view, a rising line means the sector is beating the Nifty 50.")
        one = st.selectbox("Drill into a sector's stocks", cols or list(sec.index))
        members = df[df.Sector == one].Symbol.tolist()
        st.line_chart(srb[[x for x in members if x in srb.columns]])
