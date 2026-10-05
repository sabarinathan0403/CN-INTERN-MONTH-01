
import os
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="Crypto Dashboard", page_icon="📈", layout="wide")
SNAPSHOT_CSV, HISTORY_CSV = "crypto_prices.csv", "crypto_price_history.csv"

st.markdown("""<style>
.stApp { background: #0A0E14; }
h1,h2,h3,p,span,label,div { color: #DDE3F0; }
[data-testid="stMetric"] { background:#131A2C; border:1px solid #202A44; border-radius:10px; padding:10px; }
</style>""", unsafe_allow_html=True)


def clean_money(series):
    mult = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}
    def parse(v):
        if pd.isna(v):
            return None
        t = str(v).replace("$", "").replace(",", "").strip().upper()
        try:
            return float(t[:-1]) * mult[t[-1]] if t and t[-1] in mult else float(t)
        except ValueError:
            return None
    return series.map(parse)


def clean_pct(series):
    return pd.to_numeric(series.astype(str).str.replace("%", "").str.replace("+", ""), errors="coerce")


@st.cache_data(ttl=30)
def load_data():
    snap = hist = None
    if os.path.isfile(SNAPSHOT_CSV):
        snap = pd.read_csv(SNAPSHOT_CSV)
        snap["price"] = clean_money(snap["price"])
        snap["change_24h"] = clean_pct(snap["change_24h"])
        snap["market_cap"] = clean_money(snap["market_cap"])
        snap = snap.dropna(subset=["price", "market_cap"]).reset_index(drop=True)
    if os.path.isfile(HISTORY_CSV):
        hist = pd.read_csv(HISTORY_CSV)
        hist["price"] = clean_money(hist["price"])
        hist["timestamp"] = pd.to_datetime(hist["timestamp"], errors="coerce")
        hist = hist.dropna(subset=["price", "timestamp"]).reset_index(drop=True)
    return snap, hist


st.title("📈 Crypto Price Dashboard")
if st.button("🔄 Refresh data"):
    st.cache_data.clear()
    st.rerun()

snap, hist = load_data()
if snap is None or snap.empty:
    st.warning(f"No valid data in {SNAPSHOT_CSV}. Run the tracker script first.")
    st.stop()

c1, c2, c3 = st.columns(3)
top = snap.iloc[0]
best = snap.loc[snap["change_24h"].idxmax()]
c1.metric("Coins tracked", len(snap))
c2.metric(f"Top: {top['name']}", f"${top['price']:,.2f}", f"{top['change_24h']:+.2f}%")
c3.metric(f"Best 24h: {best['name']}", f"{best['change_24h']:+.2f}%")

left, right = st.columns([1.2, 0.8])
with left:
    st.subheader("Live Snapshot")
    show = snap.copy()
    show["price"] = show["price"].map(lambda x: f"${x:,.2f}")
    show["change_24h"] = show["change_24h"].map(lambda x: f"{x:+.2f}%")
    show["market_cap"] = show["market_cap"].map(lambda x: f"${x/1e9:,.2f}B")
    st.dataframe(show[["name", "symbol", "price", "change_24h", "market_cap"]], hide_index=True, use_container_width=True)

with right:
    st.subheader("Market Cap Share")
    fig = px.pie(snap, names="symbol", values="market_cap", hole=0.6)
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", font_color="#C9D1E0", margin=dict(t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)

st.subheader("24h Change by Coin")
colors = ["#26D07C" if v >= 0 else "#FF5C5C" for v in snap["change_24h"]]
fig_bar = go.Figure(go.Bar(x=snap["symbol"], y=snap["change_24h"], marker_color=colors))
fig_bar.update_layout(paper_bgcolor="rgba(0,0,0,0)", font_color="#C9D1E0", yaxis_title="24h %")
st.plotly_chart(fig_bar, use_container_width=True)

st.subheader("Price Trend Over Time")
if hist is None or hist.empty:
    st.info("No history yet — run the tracker a few more times.")
else:
    coins = sorted(hist["name"].unique())
    chosen = st.multiselect("Coins to plot", coins, default=coins[:5])
    if chosen:
        fig_line = px.line(hist[hist["name"].isin(chosen)], x="timestamp", y="price", color="name", markers=True)
        fig_line.update_layout(paper_bgcolor="rgba(0,0,0,0)", font_color="#C9D1E0")
        st.plotly_chart(fig_line, use_container_width=True)
        #streamlit run crypto_dashboard_compact.py