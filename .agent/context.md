# Project Context — XAUUSD Telegram Signal Bot

## What This Project Is

An experimental MVP trading signal bot for XAUUSD (gold). It connects to MetaTrader 5,
reads live 1-minute candles, generates EMA/RSI-based signals with a 15-minute higher-timeframe
bias filter, tracks virtual TP/SL levels, and broadcasts signal updates to a Telegram channel.

**Not financial advice. Not a proven profitable strategy. Experimental only.**

---

## How It Runs

- Deployed on an AWS EC2 Windows Server instance
- Run manually (or via scheduled task) with: `python core.py`
- Requires MetaTrader 5 desktop app running on the same machine (MT5 Python API is Windows-only)
- Requires a `.env` file in the repo root with Telegram credentials
- No database. State is in-memory only (one active position dict). Crashes reset state.
- Logs trade events to `trades_log.csv` in the repo root (append-only CSV)

---

## Main Files

| File | Role |
|---|---|
| `core.py` | **Main runtime.** MT5 connection, signal loop, TP/SL tracking, Telegram messaging, CSV logging. |
| `get_stats.py` | **Stats reader.** Reads `trades_log.csv`, simulates exit strategies (TP1–TP4, scaling 25%), prints summary + day-wise + trade detail tables. |
| `emul.py` | **Old test emulator.** Sends random fake signals with "EXPERIMENTAL" wording. No longer used in prod. Do not run this in prod. |
| `.env` | Telegram credentials. **Never commit.** |
| `.env-example` | Template showing required env var names. |
| `trades_log.csv` | Live trade event log. Gitignored. Appended to by `core.py`. |
| `3rd-may-trades_log.csv` | Archived sample log from April 30–May 1 2026 run. |
| `3rd-may.txt` | Stats output from that archived run (produced by `get_stats.py`). |
| `README.md` | Public-facing project description. |
| `credentials.txt` | Gitignored. Likely MT5 account credentials. |
| `MW.pem` | EC2 SSH key. Untracked. Do not commit. |

---

## Env Assumptions

```
TELEGRAM_API_TOKEN=<bot token from BotFather>
TELEGRAM_CHAT_ID=<channel or group chat ID>
```

Both are loaded via `python-dotenv` at startup. If missing, Telegram calls are skipped with a logged error.

---

## Current Trading Logic Summary

### Indicators (computed on last 300 M1 candles)
- `ema_fast` = EMA(20) of close
- `ema_slow` = EMA(50) of close
- `rsi` = RSI(14)
- `rsi_ma` = Rolling MA(9) of RSI

### 15-Minute Bias Filter
- M1 data is resampled to 15m OHLC
- A separate EMA(50) is computed on the 15m closes
- `bias_buy = close > EMA50_15m`
- `bias_sell = close < EMA50_15m`
- Values are forward-filled back onto the M1 frame

### Signal Conditions
- **BUY**: EMA fast > slow (bull), price between EMAs, RSI > RSI_MA, bias_buy
- **SELL**: EMA fast < slow (bear), price between EMAs, RSI < RSI_MA, bias_sell

### Session Window
- Active: Monday–Friday, 08:00–20:00 Europe/Sofia
- Outside session: bot sleeps 30s per loop, no signals issued

### Position Management (all virtual, in-memory)
- One position at a time
- **Entry**: random 4-digit trade ID, price at signal candle close
- **TP levels**: absolute price moves [5, 10, 20, 50] → TP1–TP4
- **SL**: absolute price move of 10 (opposite direction)
- **TP hit**: checked per candle; each TP removed from remaining list once hit
- **SL hit**: position closed; Telegram SL message suppressed if any TP was already announced
- **ALL_TP_HIT**: fired when `tp_levels` list is empty (TP4 reached)
- **Session close with open trade**: logs SESSION_CLOSE using best TP reached (or current price if no TP hit)

### ROI Labels (used in CSV log and stats)
- TP1 = +0.5%, TP2 = +1%, TP3 = +2%, TP4 = +5%  (relative to SL size as 1R)
- SL = -1%

### Breakeven Protection (added 2026-05-11)
- After TP2 is hit, `position["sl"]` is moved to `position["entry"]`.
- Flag: `position["sl_moved_to_be"]` (bool) — ensures this fires only once per trade.
- Logged as event `SL_MOVED_BE` in the CSV (price = current, pips = 0).
- A Telegram reply is sent immediately after the TP2 message in the same candle batch.
- If SL fires after TP2 → trade closes at entry (0 ROI / BE), not at the original -10 SL.

---

## Telegram Message Types

| Event | Trigger |
|---|---|
| Session open | Transition into session window |
| Session close | Transition out of session window |
| Entry signal | New BUY/SELL position opened |
| TP hit | Each individual TP level crossed |
| All TP hit | All 4 TPs cleared |
| SL hit | SL crossed (suppressed if any TP already hit) |
| **BE update** | TP2 hit → SL moved to entry (🛡️ message) |
| Session close trade exit | Trade still open when session ends |
| /price reply | Bot polls for this command from the channel |

Session open/close messages use randomized Bulgarian-language text from predefined lists.
Entry, TP, SL messages use English with emoji formatting.

---

## CSV Log Schema (`trades_log.csv`)

```
trade_id, type, event, entry, price, tp_level, roi_pct, pips, time
```

- `type`: LONG or SHORT
- `event`: OPEN, TP_HIT, SL_HIT, ALL_TP_HIT, SESSION_CLOSE, SL_MOVED_BE
- `tp_level`: TP1–TP4 (only for TP_HIT rows)
- `roi_pct`: numeric ROI value (0.5, 1, 2, 5, or -1)
- `pips`: integer pips move (50, 100, 200, 500, or -100)
- `time`: Europe/Sofia datetime string

---

## Current Limitations

1. **In-memory state only.** A crash or restart loses the active position.
2. **One position at a time.** No pyramiding, no concurrent trades.
3. **No actual trade execution.** Signals are virtual; no MT5 order placement.
4. **No reconnect logic.** If MT5 disconnects mid-session, the loop errors and sleeps 5s.
5. **No Telegram send retry.** Failed sends are logged to console only.
6. **Trade IDs are random 4-digit ints.** Collisions are theoretically possible.
7. **`emul.py` uses "EXPERIMENTAL" wording** — legacy test script, should not run in prod.
8. **`MW.pem` and `credentials.txt` not in `.gitignore`.** `MW.pem` is untracked but not ignored.
9. **`get_stats.py` does not handle the `pips` column** — it ignores it and recalculates from TP_ROI map. This is fine for now.
10. **Session open/close messages are Bulgarian.** Inconsistent with English signal messages.

---

## Implementation Rules for Future Claude Code Sessions

1. **Read the relevant files before editing.** Never patch from memory.
2. **Explain the intended change before making it.** One sentence is enough.
3. **Make minimal edits.** Touch only what the task requires.
4. **After editing, summarize exactly what changed** (file, line range, what was replaced).
5. **Update `.agent/timeline.md` after every meaningful change.**
6. **Do not expose secrets.** Never read or print `.env` contents.
7. **Do not commit unless explicitly asked.**
8. **Do not rewrite the whole bot** unless the user explicitly requests a rewrite.
9. **Do not invent profitability claims.** This is experimental.
10. **Do not add complexity** (databases, async, classes, abstractions) unless asked.
11. **`emul.py` is legacy.** Do not import from it or update it unless asked.
12. **Prefer JSONL or CSV** for any new persistent logging.
13. **Keep timezone as Europe/Sofia** throughout.
14. **`get_stats.py` is a standalone script** — it must remain runnable independently of `core.py`.
