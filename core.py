import MetaTrader5 as mt5
import pandas as pd
import pytz
import time
from datetime import datetime
import requests
from dotenv import load_dotenv
import os
import random
import csv

load_dotenv()

TELEGRAM_API_TOKEN = os.getenv("TELEGRAM_API_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SYMBOL = "XAUUSD"
TIMEFRAME = mt5.TIMEFRAME_M1

TP_LEVELS = [5, 10, 20, 50]
TP_ROI_LABELS = {
    5: 0.5,
    10: 1,
    20: 2,
    50: 5
}

SL = 10
SL_ROI = -1

LOG_FILE = "trades_log.csv"
STATUS_PRINT_EVERY_SECONDS = 600
OUTSIDE_SESSION_SLEEP_SECONDS = 30

timezone = pytz.timezone("Europe/Sofia")

OPEN_MESSAGES = [
    "🌅 Сесията започна | Ботът следи XAUUSD до 20:00.",
    "🟢 Пазарният прозорец е отворен | Започваме наблюдение.",
    "⚡ Старт на сесията | Сигналите са активни до 20:00.",
    "📈 Добро утро | XAUUSD мониторингът е активен."
]

MONDAY_OPEN_MESSAGES = [
    "🌅 Нова седмица, нова сесия | Ботът отново следи XAUUSD.",
    "🟢 Понеделник старт | Мониторингът на XAUUSD е активен.",
    "📈 Пазарът се събуди | Започваме седмицата.",
    "⚡ Нова търговска седмица | Следим за сигнали."
]

CLOSE_MESSAGES = [
    "🌙 Сесията приключи | Ботът е паузиран до 08:00.",
    "🔴 Пазарният прозорец затвори | Няма нови сигнали до утре.",
    "⏸ Край на сесията | Мониторингът е спрян извън работните часове.",
    "📉 Денят приключи | Ботът спира до следващата сесия."
]

FRIDAY_CLOSE_MESSAGES = [
    "🌙 Петъчната сесия приключи | Приятен уикенд!",
    "🔴 Край на седмицата | Ботът спира до понеделник. Приятен уикенд!",
    "⏸ XAUUSD затваря за уикенда | Почиваме до понеделник.",
    "📉 Седмицата приключи | Успешен и спокоен уикенд!"
]


def now_bg():
    return datetime.now(timezone)


def bg_time_str():
    return datetime.now(timezone).strftime("%Y-%m-%d %H:%M:%S")


def is_weekday(t):
    return t.weekday() < 5


def is_friday(t):
    return t.weekday() == 4


def is_monday(t):
    return t.weekday() == 0


def in_session(t):
    return is_weekday(t) and 8 <= t.hour < 20


def build_session_open_message(t):
    if is_monday(t):
        return random.choice(MONDAY_OPEN_MESSAGES)
    return random.choice(OPEN_MESSAGES)


def build_session_close_message(t):
    if is_friday(t):
        return random.choice(FRIDAY_CLOSE_MESSAGES)
    return random.choice(CLOSE_MESSAGES)


def format_pct(value):
    return f"{value:g}%"


def get_tp_price(position, tp):
    if position["type"] == "BUY":
        return position["entry"] + tp
    return position["entry"] - tp


def log_trade_event(trade_id, trade_type, event, entry, price=None, tp_level=None, roi_pct=None):
    file_exists = os.path.exists(LOG_FILE)

    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "trade_id", "type", "event", "entry", "price",
            "tp_level", "roi_pct", "time"
        ])

        if not file_exists:
            writer.writeheader()

        writer.writerow({
            "trade_id": trade_id,
            "type": "LONG" if trade_type == "BUY" else "SHORT",
            "event": event,
            "entry": entry,
            "price": price,
            "tp_level": tp_level,
            "roi_pct": roi_pct,
            "time": bg_time_str()
        })


def send_telegram_message(message, reply_to_message_id=None):
    if not TELEGRAM_API_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ Telegram env missing")
        return None

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_API_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message
        }

        if reply_to_message_id:
            payload["reply_to_message_id"] = reply_to_message_id

        response = requests.post(url, data=payload, timeout=10)
        print(f"\n📩 Telegram response: {response.status_code}")
        print(response.text)

        return response.json() if response.ok else None

    except Exception as e:
        print(f"❌ Telegram send failed: {e}")
        return None


if not mt5.initialize():
    print("❌ MT5 initialization failed")
    quit()

print("✅ Connected to MT5")


def get_data(n=300):
    rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, n)

    if rates is None or len(rates) == 0:
        print("❌ No MT5 data returned")
        return None

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df["time"] = df["time"].dt.tz_localize("UTC").dt.tz_convert(timezone)

    return df


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


def check_signal(row):
    price = row["close"]

    price_between = (
        (price < row["ema_fast"] and price > row["ema_slow"]) or
        (price > row["ema_fast"] and price < row["ema_slow"])
    )

    bull = row["ema_fast"] > row["ema_slow"]
    bear = row["ema_fast"] < row["ema_slow"]

    buy = bull and price_between and row["rsi"] > row["rsi_ma"] and row["bias_buy"]
    sell = bear and price_between and row["rsi"] < row["rsi_ma"] and row["bias_sell"]

    return buy, sell


def build_initial_signal_message(position):
    direction = "LONG" if position["type"] == "BUY" else "SHORT"
    emoji = "🟢" if direction == "LONG" else "🔴"

    tp_lines = []
    for i, tp in enumerate(TP_LEVELS, start=1):
        tp_price = get_tp_price(position, tp)
        roi_pct = TP_ROI_LABELS[tp]
        tp_lines.append(f"🎯 TP{i}: {tp_price} ({format_pct(roi_pct)})")

    return (
        f"{emoji} {direction} Signal\n\n"
        f"🆔 Trade ID: {position['id']}\n"
        f"📍 Entry: {position['entry']}\n"
        f"🛑 SL: {position['sl']} ({format_pct(SL_ROI)})\n"
        f"{chr(10).join(tp_lines)}\n"
        f"🕒 Time: {position['opened_at']} Bulgarian time"
    )


def build_tp_update_message(tp_index, roi_pct, price):
    return (
        f"✅ TP{tp_index} hit ({format_pct(roi_pct)})\n"
        f"💰 Price: {price}\n"
        f"🕒 Time: {bg_time_str()} Bulgarian time"
    )


def build_sl_update_message(price):
    return (
        f"❌ SL hit ({format_pct(SL_ROI)})\n"
        f"💰 Price: {price}\n"
        f"🕒 Time: {bg_time_str()} Bulgarian time"
    )


def build_all_tp_hit_message(price):
    return (
        f"✅ All TP hit\n"
        f"💰 Price: {price}\n"
        f"🕒 Time: {bg_time_str()} Bulgarian time"
    )


position = None
last_candle_time = None
last_status_print = 0
last_outside_session_print = 0
last_session_state = None


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
        current_time = now_bg()
        session_active = in_session(current_time)

        if last_session_state is None:
            last_session_state = session_active

        elif session_active != last_session_state:
            if session_active:
                send_telegram_message(build_session_open_message(current_time))
                print(f"\n🟢 SESSION OPENED | {bg_time_str()} BG")
            else:
                send_telegram_message(build_session_close_message(current_time))
                print(f"\n🔴 SESSION CLOSED | {bg_time_str()} BG")

            last_session_state = session_active

        if current_ts - last_status_print >= STATUS_PRINT_EVERY_SECONDS:
            print(f"\n✅ Bot alive | {bg_time_str()} BG | Latest candle: {now} | Price: {price}")
            last_status_print = current_ts

        if not session_active:
            if current_ts - last_outside_session_print >= STATUS_PRINT_EVERY_SECONDS:
                print(f"\n⏸ Outside session | Bot paused | {bg_time_str()} BG | Allowed: Mon–Fri 08:00–20:00 BG")
                last_outside_session_print = current_ts

            time.sleep(OUTSIDE_SESSION_SLEEP_SECONDS)
            continue

        if last_candle_time == now:
            time.sleep(1)
            continue

        last_candle_time = now

        if position is not None:
            trade_updates = []
            remaining_tp = []

            for tp in position["tp_levels"]:
                tp_index = TP_LEVELS.index(tp) + 1
                roi_pct = TP_ROI_LABELS[tp]

                if position["type"] == "BUY":
                    hit = price >= position["entry"] + tp
                else:
                    hit = price <= position["entry"] - tp

                if hit:
                    msg = build_tp_update_message(tp_index, roi_pct, price)
                    trade_updates.append(msg)

                    log_trade_event(
                        trade_id=position["id"],
                        trade_type=position["type"],
                        event="TP_HIT",
                        entry=position["entry"],
                        price=price,
                        tp_level=f"TP{tp_index}",
                        roi_pct=roi_pct
                    )

                    print(f"\n🎯 TP{tp_index} HIT | Trade {position['id']} | Price: {price}")

                else:
                    remaining_tp.append(tp)

            position["tp_levels"] = remaining_tp

            for msg in trade_updates:
                send_telegram_message(
                    msg,
                    reply_to_message_id=position.get("telegram_message_id")
                )

            if (
                (position["type"] == "BUY" and price <= position["sl"]) or
                (position["type"] == "SELL" and price >= position["sl"])
            ):
                msg = build_sl_update_message(price)

                log_trade_event(
                    trade_id=position["id"],
                    trade_type=position["type"],
                    event="SL_HIT",
                    entry=position["entry"],
                    price=price,
                    roi_pct=SL_ROI
                )

                send_telegram_message(
                    msg,
                    reply_to_message_id=position.get("telegram_message_id")
                )

                print(f"\n❌ SL HIT | Trade {position['id']} | Price: {price}")
                position = None

            elif len(position["tp_levels"]) == 0:
                msg = build_all_tp_hit_message(price)

                log_trade_event(
                    trade_id=position["id"],
                    trade_type=position["type"],
                    event="ALL_TP_HIT",
                    entry=position["entry"],
                    price=price,
                    roi_pct=TP_ROI_LABELS[50]
                )

                send_telegram_message(
                    msg,
                    reply_to_message_id=position.get("telegram_message_id")
                )

                print(f"\n✅ ALL TP HIT | Trade {position['id']}")
                position = None

        if position is None:
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

                log_trade_event(
                    trade_id=trade_id,
                    trade_type=trade_type,
                    event="OPEN",
                    entry=price,
                    price=price
                )

                msg = build_initial_signal_message(position)
                telegram_response = send_telegram_message(msg)

                if telegram_response and telegram_response.get("ok"):
                    position["telegram_message_id"] = telegram_response["result"]["message_id"]

                print(f"\n🚀 {trade_type} SIGNAL | Trade {trade_id} | Entry: {price}")

        time.sleep(1)

    except Exception as e:
        print(f"\n❌ Main loop error: {e}")
        time.sleep(5)
