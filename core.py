import MetaTrader5 as mt5
import pandas as pd
import pytz
import time
from datetime import datetime
import requests
from dotenv import load_dotenv
import os
import random

# Load environment variables from .env file
load_dotenv()

# ================= SETTINGS =================
SYMBOL = "XAUUSD"
TIMEFRAME = mt5.TIMEFRAME_M1
TP_LEVELS = [5, 10, 20, 50]
SL = 10

timezone = pytz.timezone("Europe/Sofia")  # Bulgarian time zone

# ================= Telegram Bot Settings =================
API_TOKEN = os.getenv("TELEGRAM_API_TOKEN")  # Get token from .env file
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")  # Get chat ID from .env file

# Function to send a message to Telegram
def send_telegram_message(message):
    try:
        url = f"https://api.telegram.org/bot{API_TOKEN}/sendMessage"
        payload = {
            'chat_id': CHAT_ID,  # The correct chat ID goes here
            'text': message
        }
        print(f"Debug: Sending message to Telegram... {message}")  # Verbose log for debugging
        response = requests.post(url, data=payload)
        print(f"Debug: Telegram response: {response.status_code}, {response.text}")  # Log Telegram response
        return response
    except Exception as e:
        print(f"❌ Error sending Telegram message: {e}")
        return None

# ================= CONNECT =================
if not mt5.initialize():
    print("❌ MT5 initialization failed")
    quit()

print("✅ Connected to MT5")

# ================= DATA =================
def get_data(n=300):
    rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, n)
    df = pd.DataFrame(rates)

    df["time"] = pd.to_datetime(df["time"], unit="s")
    df["time"] = df["time"].dt.tz_localize("UTC").dt.tz_convert(timezone)

    return df

# ================= INDICATORS =================
def add_indicators(df):
    df["ema_fast"] = df["close"].ewm(span=20).mean()
    df["ema_slow"] = df["close"].ewm(span=50).mean()

    delta = df["close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss

    df["rsi"] = 100 - (100 / (1 + rs))
    df["rsi_ma"] = df["rsi"].rolling(9).mean()

    return df

# ================= 15M BIAS =================
def add_15m_bias(df):
    df_15 = df.resample("15min", on="time").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last"
    }).dropna()

    df_15["ema_slow"] = df_15["close"].ewm(span=50).mean()
    df_15["bias_buy"] = df_15["close"] > df_15["ema_slow"]
    df_15["bias_sell"] = df_15["close"] < df_15["ema_slow"]

    df_15 = df_15[["bias_buy", "bias_sell"]].reindex(df["time"], method="ffill")

    df["bias_buy"] = df_15["bias_buy"].values
    df["bias_sell"] = df_15["bias_sell"].values

    return df

# ================= SIGNAL =================
def check_signal(row):
    price = row["close"]
    trade_id = random.randint(1000, 9999)  # Random trade ID for simulation

    # Local Bulgarian time for trade start
    trade_time = datetime.now(timezone).strftime("%Y-%m-%d %H:%M:%S")

    price_between = (
        (price < row["ema_fast"] and price > row["ema_slow"]) or
        (price > row["ema_fast"] and price < row["ema_slow"])
    )

    bull = row["ema_fast"] > row["ema_slow"]
    bear = row["ema_fast"] < row["ema_slow"]

    buy = bull and price_between and (row["rsi"] > row["rsi_ma"]) and row["bias_buy"]
    sell = bear and price_between and (row["rsi"] < row["rsi_ma"]) and row["bias_sell"]

    # Collect the messages for all events
    messages = []

    if buy:
        messages.append(f"⚡️ EXPERIMENTAL: Buy Signal at {price}\nTrade ID: {trade_id}\nTime: {trade_time} (Bulgarian time)")
    
    if sell:
        messages.append(f"⚡️ EXPERIMENTAL: Sell Signal at {price}\nTrade ID: {trade_id}\nTime: {trade_time} (Bulgarian time)")

    # Add TP and SL hits to the message
    if position is not None:
        tp_message = []
        for tp in position["tp_levels"]:
            tp_price = position["entry"] + tp if position["type"] == "BUY" else position["entry"] - tp
            if price >= tp_price if position["type"] == "BUY" else price <= tp_price:
                tp_message.append(f"🎯 TP Hit at {tp_price}")
        
        if len(tp_message) > 0:
            messages.append("\n".join(tp_message))

        # SL check
        if (position["type"] == "BUY" and price <= position["sl"]) or \
           (position["type"] == "SELL" and price >= position["sl"]):
            messages.append("❌ SL Hit")

    if messages:
        full_message = "\n".join(messages)
        send_telegram_message(full_message)

    return buy, sell

# ================= SESSION =================
def in_session(t):
    return 8 <= t.hour < 20

# ================= STATE =================
position = None
last_candle_time = None
last_check_time = None  # Keep track of the last check time

# ================= LOOP =================
while True:
    now = datetime.now(timezone)
    if last_check_time is None or (now - last_check_time).seconds >= 300:  # 300 seconds = 5 minutes
        df = get_data()
        df = add_indicators(df)
        df = add_15m_bias(df)

        row = df.iloc[-1]
        price = row["close"]

        # ===== Only act on NEW candle =====
        if last_candle_time == row["time"]:
            time.sleep(1)
            continue

        last_candle_time = row["time"]

        print(f"\n🕒 {now} | Price: {price}")

        # ===== MANAGE TRADE =====
        if position is not None:
            new_tp = []

            for tp in position["tp_levels"]:
                tp_price = position["entry"] + tp if position["type"] == "BUY" else position["entry"] - tp

                hit = price >= tp_price if position["type"] == "BUY" else price <= tp_price

                if hit:
                    print(f"🎯 TP{TP_LEVELS.index(tp)+1} HIT (+{tp})")
                else:
                    new_tp.append(tp)

            position["tp_levels"] = new_tp

            # SL check
            if (position["type"] == "BUY" and price <= position["sl"]) or \
               (position["type"] == "SELL" and price >= position["sl"]):

                print("❌ SL HIT")
                position = None

            elif len(position["tp_levels"]) == 0:
                print("✅ ALL TP HIT")
                position = None

        # ===== ENTRY =====
        if position is None and in_session(now):
            buy, sell = check_signal(row)

            if buy or sell:
                position = {
                    "type": "BUY" if buy else "SELL",
                    "entry": price,
                    "sl": price - SL if buy else price + SL,
                    "tp_levels": TP_LEVELS.copy()
                }

                print(f"🚀 {position['type']} SIGNAL @ {price}")
                print(f"SL: {position['sl']} | TP: {TP_LEVELS}")

        last_check_time = now  # Update the last check time

    time.sleep(1)
