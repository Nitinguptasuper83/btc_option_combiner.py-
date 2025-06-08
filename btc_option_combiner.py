import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
from datetime import datetime
import time

# Supertrend calculation
def calculate_supertrend(df, period=20, multiplier=2):
    hl2 = (df['high'] + df['low']) / 2
    df['ATR'] = df['high'].rolling(period).max() - df['low'].rolling(period).min()
    df['upperband'] = hl2 + (multiplier * df['ATR'])
    df['lowerband'] = hl2 - (multiplier * df['ATR'])
    df['supertrend'] = True

    for i in range(1, len(df)):
        curr, prev = i, i - 1

        if df['close'][curr] > df['upperband'][prev]:
            df['supertrend'][curr] = True
        elif df['close'][curr] < df['lowerband'][prev]:
            df['supertrend'][curr] = False
        else:
            df['supertrend'][curr] = df['supertrend'][prev]
            if df['supertrend'][curr] and df['lowerband'][curr] < df['lowerband'][prev]:
                df['lowerband'][curr] = df['lowerband'][prev]
            if not df['supertrend'][curr] and df['upperband'][curr] > df['upperband'][prev]:
                df['upperband'][curr] = df['upperband'][prev]

    return df

# VWAP calculation
def calculate_vwap(df):
    df['vwap'] = (df['close'] * df['volume']).cumsum() / df['volume'].cumsum()
    return df

# Fetch options from Delta Exchange
@st.cache_data(ttl=60)
def fetch_options():
    url = "https://api.delta.exchange/v2/ltp"
    contracts = requests.get("https://api.delta.exchange/v2/products").json()
    all_contracts = contracts.get('result', [])
    option_contracts = [c for c in all_contracts if c['contract_type'] == 'option' and c['asset_symbol'] == 'BTC']

    calls = sorted([c for c in option_contracts if c['option_type'] == 'call'], key=lambda x: x['strike_price'])
    puts = sorted([c for c in option_contracts if c['option_type'] == 'put'], key=lambda x: x['strike_price'])

    return calls, puts

# Fetch OHLC for a contract
def fetch_ohlc(product_id, interval='1m'):
    url = f"https://api.delta.exchange/v2/history/candles?resolution={interval}&contract_id={product_id}&limit=100"
    data = requests.get(url).json()
    candles = data.get('result', [])
    df = pd.DataFrame(candles, columns=["time", "open", "high", "low", "close", "volume"])
    df['time'] = pd.to_datetime(df['time'], unit='s')
    return df

# App Layout
st.set_page_config(page_title="BTC Option Combiner", layout="wide")
st.title("📊 BTC Options Combined Chart (Delta Exchange India)")
st.caption("Select one Call and one Put. OHLC will be combined into a single chart with VWAP and Supertrend (20,2). Auto-refreshes every 60 seconds.")

# Sidebar selections
calls, puts = fetch_options()

call_strike = st.sidebar.selectbox("📈 Select CALL Option", [f"{c['strike_price']} - {c['display_name']}" for c in calls])
put_strike = st.sidebar.selectbox("📉 Select PUT Option", [f"{p['strike_price']} - {p['display_name']}" for p in puts])
interval = st.sidebar.selectbox("⏱️ Timeframe", ['1m', '5m', '15m'])

# Extract product IDs
# Extract strike price from selection (e.g. "105000 - BTC-105000-C")
selected_call_strike = float(call_strike.split(" - ")[0])
selected_put_strike = float(put_strike.split(" - ")[0])

selected_call = next(c for c in calls if c['strike_price'] == selected_call_strike)
selected_put = next(p for p in puts if p['strike_price'] == selected_put_strike)


call_df = fetch_ohlc(selected_call['id'], interval)
put_df = fetch_ohlc(selected_put['id'], interval)

# Merge & combine OHLC
combined = pd.merge(call_df, put_df, on='time', suffixes=('_call', '_put'))
combined['open'] = combined['open_call'] + combined['open_put']
combined['high'] = combined['high_call'] + combined['high_put']
combined['low'] = combined['low_call'] + combined['low_put']
combined['close'] = combined['close_call'] + combined['close_put']
combined['volume'] = combined['volume_call'] + combined['volume_put']
combined = combined[['time', 'open', 'high', 'low', 'close', 'volume']]

# Add VWAP and Supertrend
combined = calculate_vwap(combined)
combined = calculate_supertrend(combined)

# Chart
fig = go.Figure()

fig.add_trace(go.Candlestick(
    x=combined['time'],
    open=combined['open'],
    high=combined['high'],
    low=combined['low'],
    close=combined['close'],
    name='Combined'
))

fig.add_trace(go.Scatter(x=combined['time'], y=combined['vwap'], mode='lines', name='VWAP', line=dict(color='blue')))
fig.add_trace(go.Scatter(
    x=combined['time'],
    y=combined['lowerband'],
    mode='lines',
    name='Supertrend Lower',
    line=dict(color='green')
))
fig.add_trace(go.Scatter(
    x=combined['time'],
    y=combined['upperband'],
    mode='lines',
    name='Supertrend Upper',
    line=dict(color='red')
))

fig.update_layout(title="Combined Call + Put Chart", xaxis_title="Time", yaxis_title="Price", xaxis_rangeslider_visible=False)

st.plotly_chart(fig, use_container_width=True)

# Auto-refresh every 60 seconds
st.experimental_singleton.clear()
st.experimental_rerun()
