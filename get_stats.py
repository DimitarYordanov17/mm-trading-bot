import os
import pandas as pd

LOG_FILE = "trades_log.csv"

TP_ROI = {
    "TP1": 0.5,
    "TP2": 1.0,
    "TP3": 2.0,
    "TP4": 5.0,
}

SL_ROI = -1.0

STRATEGIES = {
    "Exit TP1": "TP1",
    "Exit TP2": "TP2",
    "Exit TP3": "TP3",
    "Exit TP4": "TP4",
}


def normalize_tp_level(value):
    if pd.isna(value):
        return None

    value = str(value).strip().upper()

    if value in TP_ROI:
        return value

    return None


def get_trade_strategy_result(group, target_tp):
    """
    Simulates:
    - exit when target TP is hit
    - lose if SL is hit before target TP
    - exclude if trade ends by SESSION_CLOSE before target TP/SL
    - exclude if still open/incomplete
    """

    for _, row in group.iterrows():
        event = row["event"]
        tp_level = normalize_tp_level(row.get("tp_level"))

        if event == "TP_HIT" and tp_level == target_tp:
            return TP_ROI[target_tp], "WIN"

        if event == "SL_HIT":
            return SL_ROI, "LOSS"

        if event == "SESSION_CLOSE":
            return None, "EXCLUDED"

    return None, "OPEN"


def get_scaling_result(group):
    """
    Simulates scaling:
    - 25% closed at each TP
    - if SL hits, remaining open size closes at SL_ROI
    - if SESSION_CLOSE hits, unresolved remainder is excluded from ROI
    """

    closed_fraction = 0.0
    roi = 0.0
    hit_tps = set()

    for _, row in group.iterrows():
        event = row["event"]
        tp_level = normalize_tp_level(row.get("tp_level"))

        if event == "TP_HIT" and tp_level in TP_ROI and tp_level not in hit_tps:
            hit_tps.add(tp_level)
            closed_fraction += 0.25
            roi += TP_ROI[tp_level] * 0.25

        elif event == "SL_HIT":
            remaining_fraction = max(0.0, 1.0 - closed_fraction)
            roi += SL_ROI * remaining_fraction

            if roi > 0:
                result = "WIN"
            elif roi < 0:
                result = "LOSS"
            else:
                result = "BREAKEVEN"

            return roi, result

        elif event == "SESSION_CLOSE":
            if closed_fraction == 0:
                return None, "EXCLUDED"

            if roi > 0:
                return roi, "PARTIAL_WIN"
            elif roi < 0:
                return roi, "PARTIAL_LOSS"
            else:
                return roi, "BREAKEVEN"

    if closed_fraction >= 1.0:
        return roi, "WIN"

    return None, "OPEN"


def get_be_protected_result(group):
    """
    Simulates holding to TP4 with SL moved to entry after TP2.
    - SL hit before TP2: LOSS
    - TP2 hit, then SL hit (BE fires): BREAKEVEN (0%)
    - TP2 hit, then ALL_TP_HIT: WIN (+5%)
    - SESSION_CLOSE at any point: EXCLUDED
    """
    tp2_hit = False

    for _, row in group.iterrows():
        event = row["event"]
        tp_level = normalize_tp_level(row.get("tp_level"))

        if (event == "TP_HIT" and tp_level == "TP2") or event == "SL_MOVED_BE":
            tp2_hit = True
            continue

        if event == "ALL_TP_HIT":
            return TP_ROI["TP4"], "WIN"

        if event == "SL_HIT":
            if tp2_hit:
                return 0.0, "BREAKEVEN"
            return SL_ROI, "LOSS"

        if event == "SESSION_CLOSE":
            return None, "EXCLUDED"

    return None, "OPEN"


def build_trade_rows(df):
    rows = []

    for trade_id, group in df.groupby("trade_id", sort=False):
        group = group.sort_values("time")

        opens = group[group["event"] == "OPEN"]

        if opens.empty:
            continue

        open_row = opens.iloc[0]

        base = {
            "trade_id": trade_id,
            "date": open_row["date"],
            "type": open_row["type"],
            "entry": open_row["entry"],
        }

        for strategy_name, target_tp in STRATEGIES.items():
            roi, result = get_trade_strategy_result(group, target_tp)

            rows.append({
                **base,
                "strategy": strategy_name,
                "target": target_tp,
                "roi": roi,
                "result": result,
            })

        scaling_roi, scaling_result = get_scaling_result(group)

        rows.append({
            **base,
            "strategy": "Scaling 25/25/25/25",
            "target": "TP1-TP4",
            "roi": scaling_roi,
            "result": scaling_result,
        })

        be_roi, be_result = get_be_protected_result(group)

        rows.append({
            **base,
            "strategy": "Exit TP4 + BE at TP2",
            "target": "TP4",
            "roi": be_roi,
            "result": be_result,
        })

    return pd.DataFrame(rows)


def print_strategy_summary(stats):
    print("\n===== STRATEGY SUMMARY =====")

    for strategy, group in stats.groupby("strategy", sort=False):
        finished = group[group["roi"].notna()].copy()

        if finished.empty:
            print(f"\n{strategy}")
            print("No finalized trades.")
            continue

        wins = (finished["roi"] > 0).sum()
        losses = (finished["roi"] < 0).sum()
        breakeven = (finished["roi"] == 0).sum()
        total = len(finished)

        win_rate = wins / total * 100
        total_roi = finished["roi"].sum()
        avg_roi = finished["roi"].mean()

        excluded = (group["result"] == "EXCLUDED").sum()
        open_trades = (group["result"] == "OPEN").sum()

        print(f"\n{strategy}")
        print(f"Finalized trades: {total}")
        print(f"Wins: {wins}")
        print(f"Losses: {losses}")
        print(f"Breakeven: {breakeven}")
        print(f"Win rate: {win_rate:.2f}%")
        print(f"Total ROI: {total_roi:.2f}%")
        print(f"Average ROI/trade: {avg_roi:.2f}%")
        print(f"Excluded/session-close: {excluded}")
        print(f"Still open/incomplete: {open_trades}")


def print_day_wise_summary(stats):
    print("\n===== DAY-WISE ROI BY STRATEGY =====")

    finished = stats[stats["roi"].notna()].copy()

    if finished.empty:
        print("No finalized strategy results.")
        return

    day_stats = finished.groupby(["date", "strategy"], sort=False).agg(
        trades=("trade_id", "count"),
        wins=("roi", lambda x: (x > 0).sum()),
        losses=("roi", lambda x: (x < 0).sum()),
        roi=("roi", "sum"),
    ).reset_index()

    for _, row in day_stats.iterrows():
        print(
            f"{row['date']} | "
            f"{row['strategy']} | "
            f"Trades: {row['trades']} | "
            f"Wins: {row['wins']} | "
            f"Losses: {row['losses']} | "
            f"ROI: {row['roi']:.2f}%"
        )


def print_trade_details(stats):
    print("\n===== TRADE DETAILS =====")

    display = stats.copy()
    display["roi"] = display["roi"].apply(
        lambda x: "" if pd.isna(x) else f"{x:.2f}%"
    )

    print(display.to_string(index=False))


def print_be_summary(df):
    print("\n===== BREAKEVEN-PROTECTED TRADE OUTCOMES =====")

    sl_before_tp2_count = 0
    be_outcomes = []

    for trade_id, group in df.groupby("trade_id", sort=False):
        group = group.sort_values("time")

        tp2_hit = False
        after_tp2 = False
        best_tp_after = None
        terminal = "OPEN"

        for _, row in group.iterrows():
            event = row["event"]
            tp_level = normalize_tp_level(row.get("tp_level"))

            if (event == "TP_HIT" and tp_level == "TP2") or event == "SL_MOVED_BE":
                tp2_hit = True
                after_tp2 = True
                continue

            if not after_tp2:
                if event == "SL_HIT":
                    sl_before_tp2_count += 1
                    break
                continue

            if event == "TP_HIT" and tp_level in ("TP3", "TP4"):
                best_tp_after = tp_level
            elif event == "ALL_TP_HIT":
                terminal = "TP4"
                break
            elif event == "SL_HIT":
                terminal = "BE"
                break
            elif event == "SESSION_CLOSE":
                terminal = "SESSION_CLOSE"
                break

        if not tp2_hit:
            continue

        if terminal == "OPEN" and best_tp_after:
            terminal = best_tp_after

        be_outcomes.append(terminal)

    be_total = len(be_outcomes)

    print(f"Trades where SL hit before TP2 (no BE activated): {sl_before_tp2_count}")

    if be_total == 0:
        print("No trades with TP2 hit found.")
        return

    counts = {k: be_outcomes.count(k) for k in ("BE", "TP3", "TP4", "SESSION_CLOSE", "OPEN")}

    print(f"\nTrades where TP2 hit (BE active): {be_total}")
    print(f"  → Ended at BE (SL triggered at entry): {counts['BE']}")
    print(f"  → Best result TP3 (then unresolved): {counts['TP3']}")
    print(f"  → Reached TP4 / ALL_TP: {counts['TP4']}")
    print(f"  → Ended at session close: {counts['SESSION_CLOSE']}")
    print(f"  → Still open/incomplete: {counts['OPEN']}")


def main():
    if not os.path.exists(LOG_FILE):
        print("No trades_log.csv found.")
        return

    df = pd.read_csv(LOG_FILE)

    if df.empty:
        print("trades_log.csv is empty.")
        return

    required_cols = {"trade_id", "type", "event", "entry", "price", "tp_level", "roi_pct", "time"}
    missing = required_cols - set(df.columns)

    if missing:
        print(f"Missing required columns: {sorted(missing)}")
        return

    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    df = df.dropna(subset=["time"])

    df["date"] = df["time"].dt.date
    df["event"] = df["event"].astype(str).str.strip().str.upper()
    df["tp_level"] = df["tp_level"].apply(normalize_tp_level)
    df["entry"] = pd.to_numeric(df["entry"], errors="coerce")
    df["price"] = pd.to_numeric(df["price"], errors="coerce")

    stats = build_trade_rows(df)

    if stats.empty:
        print("No usable trades found.")
        return

    print_strategy_summary(stats)
    print_day_wise_summary(stats)
    print_trade_details(stats)
    print_be_summary(df)


if __name__ == "__main__":
    main()
