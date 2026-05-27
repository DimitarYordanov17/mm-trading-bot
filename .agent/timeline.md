# Project Timeline

---

## 2026-05-11

### Initial Claude Code onboarding

**What changed:**
- Inspected full repo structure and read all source files.
- Created `.agent/context.md` with project overview, file map, trading logic summary, CSV schema, limitations, and implementation rules.
- Created `.agent/timeline.md` (this file).

**Files changed:**
- `.agent/context.md` (new)
- `.agent/timeline.md` (new)

**No runtime code changed.**

**Why:**
Establish a persistent knowledge base so future Claude Code sessions start with full context
instead of re-deriving it from scratch.

---

## 2026-05-11

### Cooldown after full-loss SL — all directions blocked (updated 2026-05-23)

**What changed:**
- `core.py`: Changed `last_full_loss_time` from `{"BUY": None, "SELL": None}` to a single `None` timestamp.
- `core.py`: Cooldown recording now sets `last_full_loss_time = current_ts` (no direction key).
- `core.py`: Cooldown check now reads `last_full_loss_time` directly (blocks both BUY and SELL).
- Updated print messages to remove direction wording.

**Files changed:**
- `core.py`
- `.agent/context.md`
- `.agent/timeline.md`

**Why:**
Algorithm was failing repeatedly — extending the cooldown to all directions prevents re-entry in either direction after a clean loss, not just the same one.

**Risks / follow-ups:**
- Cooldown state is in-memory only — a process restart resets the timestamp. Acceptable for MVP.
- If SL fires due to BE (SL moved to entry after TP2), `max_tp_index_reached >= 2` so cooldown does NOT trigger. Correct — that's not a full loss.
- Cooldown does not clear on session close; it expires naturally by timestamp.

---

### Breakeven (BE) protection after TP2

**What changed:**
- `core.py`: Added `build_be_message()` function.
- `core.py`: Added `"sl_moved_to_be": False` to position init dict.
- `core.py`: Inside the TP hit loop, when `tp_index == 2` and flag not set:
  - moves `position["sl"]` to `position["entry"]`
  - sets `sl_moved_to_be = True`
  - appends BE Telegram message to the same batch as the TP2 message
  - logs `SL_MOVED_BE` event to CSV (pips=0)
- `get_stats.py`: Added `get_be_protected_result()` — simulates TP4 exit with BE at TP2.
- `get_stats.py`: Added `"Exit TP4 + BE at TP2"` strategy row in `build_trade_rows()`.
- `get_stats.py`: Added `print_be_summary()` — separate section showing outcome distribution for BE-activated trades.
- `get_stats.py`: Called `print_be_summary(df)` at end of `main()`.
- `.agent/context.md`: Updated to reflect new position flag, event type, and message type.

**Files changed:**
- `core.py`
- `get_stats.py`
- `.agent/context.md`
- `.agent/timeline.md`

**Why:**
No-loss / breakeven protection after TP2 is a standard risk management rule. Prevents a winning trade from turning into a full loss after price reaches TP2.

**Historical simulation note:**
Existing logs are sufficient to simulate this retroactively. Event order determines outcome: if `TP_HIT(TP2)` appears before `SL_HIT`, the sim credits BE (0%) instead of loss (-1%). In the current sample data (April 30–May 1), no trade had a TP2→SL sequence, so the new strategy shows identical results to "Exit TP4" on that dataset.

**Risks / follow-ups:**
- The BE message is sent as part of the same candle's `trade_updates` batch, so it will be sent immediately after the TP2 message. Message order is: TP2 → BE (correct).
- If TP2 and TP3 hit on the same candle: order is TP2 message → BE message → TP3 message (correct — BE fires exactly once).
- SL check runs after all TP messages are sent. With new SL at entry and price above entry (TP2+ hit), the SL won't misfire on the same candle.

---

---

## 2026-05-27

### USD High-Impact News Filter

**What changed:**
- `core.py`: Added `from datetime import timedelta` to existing datetime import.
- `core.py`: Added three config constants — `USE_NEWS_FILTER`, `MINUTES_BEFORE_NEWS`, `MINUTES_AFTER_NEWS`.
- `core.py`: Added `is_high_impact_news_time()` function — queries MT5 economic calendar for USD high-importance events in a ±15 min UTC window around now.
- `core.py`: Main loop signal guard now checks `is_high_impact_news_time()` after cooldown, before opening any trade.
- `.agent/context.md`: Added "News Filter" section under trading logic.

**Files changed:**
- `core.py`
- `.agent/context.md`
- `.agent/timeline.md`

**Why:**
Prevent trade entries around high-impact USD news (e.g. NFP, CPI) where spread widens and price moves are unpredictable.

**Risks / follow-ups:**
- Requires broker to supply MT5 economic calendar data. If `calendar_value_history` returns `None`, the filter silently passes and trading continues — safe fail-open behavior.
- `USE_NEWS_FILTER = True` can be toggled to `False` to disable without touching logic.
- Filter is only evaluated when a signal fires, not on every tick — negligible performance impact.

---

**Original onboarding risks / follow-ups:**
- `MW.pem` is untracked but not in `.gitignore` — worth adding to avoid accidental commits.
- Session open/close messages are Bulgarian while signal messages are English — inconsistency to address when cleaning up message formatting.
- `emul.py` has "EXPERIMENTAL" wording in Telegram messages — confirm it is never run in prod.
- Old archived log (`3rd-may-trades_log.csv`) uses different `roi_pct` scale than current code — not a bug since it's archived, but worth noting.
