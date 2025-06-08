import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time
import numpy as np

st.set_page_config(page_title="BTC Option Combiner", layout="wide")

# ───────────────────────────────────────
# 🧮 Technical Indicators
# ───────────────────────────────────────
def calculate_vwap(df):
    q = df['volume']
    p = df['close']
    vwap = (p * q).cumsum() / q.cumsum()
    return vwap

def supertrend(df, period=20, multiplier=2):
    hl2 = (df['high'] + df['low']) / 2
    atr = df['high'].rolling(period).max() - df['low'].rolling(period).min()
    upperband = hl2 + multiplier * atr
    lowerband = hl2 - multiplier * atr
    supertrend = [np.nan] * len(df)
    direction = [True] * len(df)

    for i in range(1, len(df)):
        if df['close'][i] > upperband[i-1]:
            direction[i] = True
        elif df['close'][i] < lowerband[i-1]:
            direction[i] = False
        else:
            direction[i] = direction[i-1]
            upperband[i] = min(upperband[i], upperband[i-1]) if direction[i] else upperband[i]
            lowerband[i] = max(lowerband[i], lowerband[i-1]) if not direction[i] else lowerband[i]

        supertrend[i] = lowerband[i] if direction[i] else upperband[i]

    return supertrend

# ───────────────────────────────────────
# 🔌 Deribit API Helpers
# ───────────────────────────────────────
@st.cache_data(ttl=60)
def get_option_instruments():
    url = "https://www.deribit.com/api/v2/public/get_instruments?currency=BTC&kind=option&expired=false"
    r = requests.get(url)
    return r.json()["result"]

@st.cache_data(ttl=60)
def get_ohlc(instrument_name, timeframe):
    # Convert timeframe for Deribit
    resolution_map = {
        "1 min": 60,
        "5 min": 300,
        "15 min": 900,
        "1 hour": 3600,
        "4 hours": 14400,
        "1 day": 86400
    }
    end = int(time.time() * 1000)
    start = end - resolution_map[timeframe] * 1000 * 100

    url = f"https://www.deribit.com/api/v2/public/get_tradingview_chart_data?instrument_name={instrument_name}&start_timestamp={start}&end_timestamp={end}&resolution={resolution_map[timeframe]}"
    r = requests.get(url)
    data = r.json()["result"]
    df = pd.DataFrame(data)
    if df.empty: return None

    df = df.rename(columns={
        "ticks": "timestamp",
        "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"
    })
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit='ms')
    return df

# ───────────────────────────────────────
# 🎛️ Sidebar - User Controls
# ───────────────────────────────────────
st.sidebar.title("🔘 Select Options")
instruments = get_option_instruments()

calls = [i for i in instruments if i['option_type'] == 'call']
puts = [i for i in instruments if i['option_type'] == 'put']

call_options = [c["instrument_name"] for c in sorted(calls, key=lambda x: x["strike"])]
put_options = [p["instrument_name"] for p in sorted(puts, key=lambda x: x["strike"])]

selected_call = st.sidebar.selectbox("📈 Call Option", call_options)
selected_put = st.sidebar.selectbox("📉 Put Option", put_options)

timeframe = st.sidebar.selectbox("⏱️ Timeframe", ["1 min", "5 min", "15 min", "1 hour", "4 hours", "1 day"])

# ───────────────────────────────────────
# 📊 Fetch & Combine Data
# ───────────────────────────────────────
df_call = get_ohlc(selected_call, timeframe)
df_put = get_ohlc(selected_put, timeframe)

if df_call is not None and df_put is not None:
    df = df_call.copy()
    df["open"] += df_put["open"]
    df["high"] += df_put["high"]
    df["low"] += df_put["low"]
    df["close"] += df_put["close"]
    df["volume"] += df_put["volume"]

    df["vwap"] = calculate_vwap(df)
    df["supertrend"] = supertrend(df)

    # ───────────────────────────────────────
    # 📈 Plotting Chart
    # ───────────────────────────────────────
    fig = go.Figure()

    fig.add_trace(go.Candlestick(
        x=df["timestamp"],
        open=df["open"],
        high=df["high"],
        low=df["low"],
        close=df["close"],
        name="Combined OHLC"
    ))

    fig.add_trace(go.Scatter(x=df["timestamp"], y=df["vwap"], mode="lines", name="VWAP", line=dict(color="blue")))
    fig.add_trace(go.Scatter(x=df["timestamp"], y=df["supertrend"], mode="lines", name="Supertrend", line=dict(color="green")))

    fig.update_layout(title="📊 Combined BTC Option Chart (Call + Put)", xaxis_title="Time", yaxis_title="Price", xaxis_rangeslider_visible=False)

    st.plotly_chart(fig, use_container_width=True)
else:
    st.error("⚠️ Could not fetch data for one or both selected options.")
