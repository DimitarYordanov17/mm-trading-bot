import MetaTrader5 as mt5
import pandas as pd
import pytz
import time
from datetime import datetime
import requests
from dotenv import load_dotenv
import os
import random

# ================= ENV =================
load_dotenv()

TELEGRAM_API_TOKEN = os.getenv("TELEGRAM_API_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ================= SETTINGS =================
SYMBOL = "XAUUSD"
TIMEFRAME = mt5.TIMEFRAME_M1

TP_LEVELS = [5, 10, 20, 50]
SL = 10

STATUS_PRINT_EVERY_SECONDS = 600

timezone = pytz.timezone("Europe/Sofia")


# ================= TELEGRAM =================
def send_telegram_message(message, reply_to_message_id=None):
    if not TELEGRAM_API_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ Telegram env missing: TELEGRAM_API_TOKEN or TELEGRAM_CHAT_ID")
        return None

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_API_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message
        }

        if reply_to_message_id:
            payload["reply_to_message_id"] = reply_to_message_id

        print("\n📤 Sending Telegram message:")
        print(message)

        response = requests.post(url, data=payload, timeout=10)

        print(f"📩 Telegram response: {response.status_code}")
        print(response.text)

        return response.json() if response.ok else None

    except Exception as e:
        print(f"❌ Telegram send failed: {e}")
        return None


# ================= CONNECT =================
if not mt5.initialize():
    print("❌ MT5 initialization failed")
    quit()

print("✅ Connected to MT5")


# ================= DATA =================
def get_data(n=300):
    rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, n)

    if rates is None or len(rates) == 0:
        print("❌ No MT5 data returned")
        return None

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

    price_between = (
        (price < row["ema_fast"] and price > row["ema_slow"]) or
        (price > row["ema_fast"] and price < row["ema_slow"])
    )

    bull = row["ema_fast"] > row["ema_slow"]
    bear = row["ema_fast"] < row["ema_slow"]

    buy = bull and price_between and (row["rsi"] > row["rsi_ma"]) and row["bias_buy"]
    sell = bear and price_between and (row["rsi"] < row["rsi_ma"]) and row["bias_sell"]

    return buy, sell


# ================= SESSION =================
def in_session(t):
    return 8 <= t.hour < 20


# ================= HELPERS =================
def bg_time_str():
    return datetime.now(timezone).strftime("%Y-%m-%d %H:%M:%S")


def build_initial_signal_message(position):
    direction = "LONG" if position["type"] == "BUY" else "SHORT"
    emoji = "🟢" if direction == "LONG" else "🔴"

    return (
        f"{emoji} {direction} Signal\n\n"
        f"🆔 Trade ID: {position['id']}\n"
        f"📍 Entry: {position['entry']}\n"
        f"🕒 Time: {position['opened_at']} Bulgarian time"
    )


def build_tp_update_message(tp_index, tp_percent, price):
    return (
        f"✅ TP{tp_index} hit ({tp_percent}%)\n"
        f"💰 Price: {price}\n"
        f"🕒 Time: {bg_time_str()} Bulgarian time"
    )


def build_sl_update_message(price):
    return (
        f"❌ SL hit\n"
        f"💰 Price: {price}\n"
        f"🕒 Time: {bg_time_str()} Bulgarian time"
    )


def build_all_tp_hit_message(price):
    return (
        f"✅ All TP hit\n"
        f"💰 Price: {price}\n"
        f"🕒 Time: {bg_time_str()} Bulgarian time"
    )


# ================= STATE =================
position = None
last_candle_time = None
last_status_print = 0


# ================= LOOP =================
while True:
    try:
        df = get_data()

        if df is None:
            time.sleep(1)
            continue

        df = add_indicators(df)
        df = add_15m_bias(df)

        row = df.iloc[-1]
        price = row["close"]
        now = row["time"]

        current_ts = time.time()
        if current_ts - last_status_print >= STATUS_PRINT_EVERY_SECONDS:
            print(f"\n✅ Bot alive | {bg_time_str()} BG | Latest candle: {now} | Price: {price}")
            last_status_print = current_ts

        if last_candle_time == now:
            time.sleep(1)
            continue

        last_candle_time = now

        # ===== MANAGE EXISTING TRADE =====
        if position is not None:
            trade_updates = []
            remaining_tp = []

            for tp in position["tp_levels"]:
                tp_index = TP_LEVELS.index(tp) + 1

                if position["type"] == "BUY":
                    tp_price = position["entry"] + tp
                    hit = price >= tp_price
                else:
                    tp_price = position["entry"] - tp
                    hit = price <= tp_price

                if hit:
                    msg = build_tp_update_message(tp_index, tp, price)
                    print(f"\n🎯 TP{tp_index} HIT | Trade {position['id']} | Price: {price}")
                    trade_updates.append(msg)
                else:
                    remaining_tp.append(tp)

            position["tp_levels"] = remaining_tp

            for msg in trade_updates:
                send_telegram_message(
                    msg,
                    reply_to_message_id=position.get("telegram_message_id")
                )

            # ===== SL CHECK =====
            if (
                (position["type"] == "BUY" and price <= position["sl"]) or
                (position["type"] == "SELL" and price >= position["sl"])
            ):
                msg = build_sl_update_message(price)

                print(f"\n❌ SL HIT | Trade {position['id']} | Price: {price}")

                send_telegram_message(
                    msg,
                    reply_to_message_id=position.get("telegram_message_id")
                )

                position = None

            elif len(position["tp_levels"]) == 0:
                msg = build_all_tp_hit_message(price)

                print(f"\n✅ ALL TP HIT | Trade {position['id']}")

                send_telegram_message(
                    msg,
                    reply_to_message_id=position.get("telegram_message_id")
                )

                position = None

        # ===== ENTRY =====
        if position is None and in_session(now):
            buy, sell = check_signal(row)

            if buy or sell:
                trade_type = "BUY" if buy else "SELL"
                trade_id = random.randint(1000, 9999)

                position = {
                    "id": trade_id,
                    "type": trade_type,
                    "entry": price,
                    "sl": price - SL if buy else price + SL,
                    "tp_levels": TP_LEVELS.copy(),
                    "opened_at": bg_time_str(),
                    "telegram_message_id": None
                }

                msg = build_initial_signal_message(position)

                print(f"\n🚀 {trade_type} SIGNAL | Trade {trade_id} | Entry: {price}")
                print(f"SL: {position['sl']} | TP levels: {position['tp_levels']}")

                telegram_response = send_telegram_message(msg)

                if telegram_response and telegram_response.get("ok"):
                    position["telegram_message_id"] = telegram_response["result"]["message_id"]
                    print(f"✅ Stored Telegram message ID: {position['telegram_message_id']}")
                else:
                    print("⚠️ Could not store Telegram message ID. Updates may not reply correctly.")

        time.sleep(1)

    except Exception as e:
        print(f"\n❌ Main loop error: {e}")
        time.sleep(5)
