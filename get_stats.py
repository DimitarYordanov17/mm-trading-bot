import pandas as pd
import os

LOG_FILE = "trades_log.csv"


def main():
    if not os.path.exists(LOG_FILE):
        print("No trades_log.csv found.")
        return

    df = pd.read_csv(LOG_FILE)

    if df.empty:
        print("trades_log.csv is empty.")
        return

    df["time"] = pd.to_datetime(df["time"])
    df["date"] = df["time"].dt.date
    df["roi_pct"] = pd.to_numeric(df["roi_pct"], errors="coerce")

    closed_events = df[df["event"].isin(["TP_HIT", "SL_HIT", "ALL_TP_HIT"])].copy()

    if closed_events.empty:
        print("No closed trade events yet.")
        return

    final_rows = []

    for trade_id, group in df.groupby("trade_id"):
        group = group.sort_values("time")

        opens = group[group["event"] == "OPEN"]
        events = group[group["event"].isin(["TP_HIT", "SL_HIT", "ALL_TP_HIT"])]

        if opens.empty or events.empty:
            continue

        open_row = opens.iloc[0]

        tp_events = events[events["event"] == "TP_HIT"]
        sl_events = events[events["event"] == "SL_HIT"]
        all_tp_events = events[events["event"] == "ALL_TP_HIT"]

        if not all_tp_events.empty:
            final_roi = 5
            result = "WIN"
        elif not tp_events.empty:
            final_roi = tp_events["roi_pct"].max()
            result = "WIN"
        elif not sl_events.empty:
            final_roi = -1
            result = "LOSS"
        else:
            continue

        final_rows.append({
            "trade_id": trade_id,
            "date": open_row["date"],
            "type": open_row["type"],
            "entry": open_row["entry"],
            "final_roi": final_roi,
            "result": result
        })

    if not final_rows:
        print("No finalized trades yet.")
        return

    stats = pd.DataFrame(final_rows)

    total_trades = len(stats)
    wins = len(stats[stats["result"] == "WIN"])
    losses = len(stats[stats["result"] == "LOSS"])
    win_rate = wins / total_trades * 100
    total_roi = stats["final_roi"].sum()
    avg_roi = stats["final_roi"].mean()

    print("\n===== OVERALL STATS =====")
    print(f"Total finalized trades: {total_trades}")
    print(f"Wins: {wins}")
    print(f"Losses: {losses}")
    print(f"Win rate: {win_rate:.2f}%")
    print(f"Total ROI: {total_roi:.2f}%")
    print(f"Average ROI/trade: {avg_roi:.2f}%")

    print("\n===== DAY-WISE ROI =====")
    day_stats = stats.groupby("date").agg(
        trades=("trade_id", "count"),
        wins=("result", lambda x: (x == "WIN").sum()),
        losses=("result", lambda x: (x == "LOSS").sum()),
        roi=("final_roi", "sum")
    ).reset_index()

    for _, row in day_stats.iterrows():
        print(
            f"{row['date']} | "
            f"Trades: {row['trades']} | "
            f"Wins: {row['wins']} | "
            f"Losses: {row['losses']} | "
            f"ROI: {row['roi']:.2f}%"
        )

    print("\n===== TRADE DETAILS =====")
    print(stats.to_string(index=False))


if __name__ == "__main__":
    main()
