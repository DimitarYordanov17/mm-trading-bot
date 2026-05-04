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

PIPS_PER_DOLLAR = 100

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

telegram_last_update_id = None


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


def price_move_to_pips(move):
    return int(round(move * PIPS_PER_DOLLAR))


def format_pips(pips):
    sign = "+" if pips > 0 else ""
    return f"{sign}{pips} pips"


def get_tp_pips(tp):
    return price_move_to_pips(tp)


def get_sl_pips():
    return -price_move_to_pips(SL)


def get_tp_price(position, tp):
    if position["type"] == "BUY":
        return round(position["entry"] + tp, 2)
    return round(position["entry"] - tp, 2)


def calculate_unrealized_roi(position, price):
    if position["type"] == "BUY":
        move = price - position["entry"]
    else:
        move = position["entry"] - price

    roi = move / SL
    return max(SL_ROI, min(5, roi))


def calculate_unrealized_pips(position, price):
    if position["type"] == "BUY":
        move = price - position["entry"]
    else:
        move = position["entry"] - price

    pips = price_move_to_pips(move)
    return max(get_sl_pips(), min(get_tp_pips(50), pips))


def calculate_session_close_roi(position, price):
    max_roi_reached = position.get("max_roi_reached", 0)

    if max_roi_reached > 0:
        return max_roi_reached

    return calculate_unrealized_roi(position, price)


def calculate_session_close_pips(position, price):
    max_pips_reached = position.get("max_pips_reached", 0)

    if max_pips_reached > 0:
        return max_pips_reached

    return calculate_unrealized_pips(position, price)


def ensure_log_schema():
    expected_columns = [
        "trade_id", "type", "event", "entry", "price",
        "tp_level", "roi_pct", "pips", "time"
    ]

    if not os.path.exists(LOG_FILE):
        return

    try:
        df = pd.read_csv(LOG_FILE)

        changed = False
        for col in expected_columns:
            if col not in df.columns:
                df[col] = ""
                changed = True

        if changed:
            df = df[expected_columns]
            df.to_csv(LOG_FILE, index=False, encoding="utf-8")

    except Exception as e:
        print(f"❌ Failed to migrate log schema: {e}")


def log_trade_event(trade_id, trade_type, event, entry, price=None, tp_level=None, roi_pct=None, pips=None):
    file_exists = os.path.exists(LOG_FILE)

    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "trade_id", "type", "event", "entry", "price",
            "tp_level", "roi_pct", "pips", "time"
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
            "pips": pips,
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


def poll_telegram_commands(price):
    global telegram_last_update_id

    if not TELEGRAM_API_TOKEN or not TELEGRAM_CHAT_ID:
        return

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_API_TOKEN}/getUpdates"
        params = {
            "timeout": 1,
            "allowed_updates": ["message", "channel_post"]
        }

        if telegram_last_update_id is not None:
            params["offset"] = telegram_last_update_id + 1

        response = requests.get(url, params=params, timeout=5)

        if not response.ok:
            print(f"❌ Telegram getUpdates failed: {response.status_code}")
            return

        data = response.json()

        for update in data.get("result", []):
            telegram_last_update_id = update["update_id"]

            message = update.get("message") or update.get("channel_post")
            if not message:
                continue

            chat_id = str(message.get("chat", {}).get("id"))
            text = str(message.get("text", "")).strip().lower()
            message_id = message.get("message_id")

            if chat_id != str(TELEGRAM_CHAT_ID):
                continue

            command = text.split()[0] if text else ""

            if command.startswith("/price"):
                send_telegram_message(
                    build_price_message(price),
                    reply_to_message_id=message_id
                )

    except Exception as e:
        print(f"❌ Telegram command polling failed: {e}")


def build_price_message(price):
    return f"💰 XAUUSD Price: {price}"


def build_session_close_trade_message(position, price, roi_pct, pips):
    return (
        f"⏸ Trade closed at session end\n"
        f"🆔 Trade ID: {position['id']}\n"
        f"💰 Close price: {price}\n"
        f"📊 Session result: {format_pips(pips)}"
    )


if not mt5.initialize():
    print("❌ MT5 initialization failed")
    quit()

ensure_log_schema()

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
        tp_lines.append(f"🎯 TP{i}: {tp_price}")

    return (
        f"{emoji} {direction} Signal\n\n"
        f"🆔 Trade ID: {position['id']}\n"
        f"📍 Entry: {position['entry']}\n\n"
        f"🛑 SL: {round(position['sl'], 2)}\n"
        f"{chr(10).join(tp_lines)}"
    )


def build_tp_update_message(tp_index, pips, price, position):
    direction = "LONG" if position["type"] == "BUY" else "SHORT"
    tp_price = get_tp_price(position, TP_LEVELS[tp_index - 1])

    return (
        f"✅ XAUUSD {direction} — TP{tp_index} HIT\n\n"
        f"🎯 TP{tp_index}: {tp_price}\n"
        f"📊 Move: {format_pips(pips)}\n"
        f"💰 Current Price: {price}"
    )


def build_sl_update_message(price, position):
    direction = "LONG" if position["type"] == "BUY" else "SHORT"

    return (
        f"❌ XAUUSD {direction} — SL HIT\n\n"
        f"📊 Move: {format_pips(get_sl_pips())}\n"
        f"💰 Current Price: {price}"
    )


def build_all_tp_hit_message(price, position):
    direction = "LONG" if position["type"] == "BUY" else "SHORT"
    tp_price = get_tp_price(position, 50)

    return (
        f"✅ XAUUSD {direction} — ALL TP HIT\n\n"
        f"🎯 TP4: {tp_price}\n"
        f"📊 Move: {format_pips(get_tp_pips(50))}\n"
        f"💰 Current Price: {price}"
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

        poll_telegram_commands(price)

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
                if position is not None:
                    session_close_roi = calculate_session_close_roi(position, price)
                    session_close_pips = calculate_session_close_pips(position, price)

                    log_trade_event(
                        trade_id=position["id"],
                        trade_type=position["type"],
                        event="SESSION_CLOSE",
                        entry=position["entry"],
                        price=price,
                        roi_pct=session_close_roi,
                        pips=session_close_pips
                    )

                    send_telegram_message(
                        build_session_close_trade_message(
                            position,
                            price,
                            session_close_roi,
                            session_close_pips
                        ),
                        reply_to_message_id=position.get("telegram_message_id")
                    )

                    print(
                        f"\n⏸ SESSION CLOSE TRADE EXIT | "
                        f"Trade {position['id']} | Price: {price} | "
                        f"ROI: {session_close_roi} | Pips: {session_close_pips}"
                    )

                    position = None

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
                pips = get_tp_pips(tp)

                if position["type"] == "BUY":
                    hit = price >= position["entry"] + tp
                else:
                    hit = price <= position["entry"] - tp

                if hit:
                    msg = build_tp_update_message(tp_index, pips, price, position)
                    trade_updates.append(msg)

                    position["max_roi_reached"] = max(
                        position.get("max_roi_reached", 0),
                        roi_pct
                    )

                    position["max_pips_reached"] = max(
                        position.get("max_pips_reached", 0),
                        pips
                    )

                    log_trade_event(
                        trade_id=position["id"],
                        trade_type=position["type"],
                        event="TP_HIT",
                        entry=position["entry"],
                        price=price,
                        tp_level=f"TP{tp_index}",
                        roi_pct=roi_pct,
                        pips=pips
                    )

                    print(f"\n🎯 TP{tp_index} HIT | Trade {position['id']} | Price: {price} | Pips: {pips}")

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
                msg = build_sl_update_message(price, position)

                log_trade_event(
                    trade_id=position["id"],
                    trade_type=position["type"],
                    event="SL_HIT",
                    entry=position["entry"],
                    price=price,
                    roi_pct=SL_ROI,
                    pips=get_sl_pips()
                )

                send_telegram_message(
                    msg,
                    reply_to_message_id=position.get("telegram_message_id")
                )

                print(f"\n❌ SL HIT | Trade {position['id']} | Price: {price} | Pips: {get_sl_pips()}")
                position = None

            elif len(position["tp_levels"]) == 0:
                msg = build_all_tp_hit_message(price, position)

                log_trade_event(
                    trade_id=position["id"],
                    trade_type=position["type"],
                    event="ALL_TP_HIT",
                    entry=position["entry"],
                    price=price,
                    roi_pct=TP_ROI_LABELS[50],
                    pips=get_tp_pips(50)
                )

                send_telegram_message(
                    msg,
                    reply_to_message_id=position.get("telegram_message_id")
                )

                print(f"\n✅ ALL TP HIT | Trade {position['id']} | Pips: {get_tp_pips(50)}")
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
                    "telegram_message_id": None,
                    "max_roi_reached": 0,
                    "max_pips_reached": 0
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
