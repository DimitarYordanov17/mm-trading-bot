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

### Same-direction cooldown after full-loss SL

**What changed:**
- `core.py`: Added `SAME_DIRECTION_COOLDOWN_SECONDS = 30 * 60` constant.
- `core.py`: Added `last_full_loss_time = {"BUY": None, "SELL": None}` runtime global.
- `core.py`: In the SL hit block, if `max_tp_index_reached == 0` (no TPs hit): records `current_ts` for that direction.
- `core.py`: In the signal open block, before creating a position: checks if the signal direction is in cooldown. If yes, skips the trade with a console print. If no, proceeds as before.

**Files changed:**
- `core.py`
- `.agent/context.md`
- `.agent/timeline.md`

**Why:**
Avoid re-entering the same direction immediately after a clean loss (no partial profit). Opposite direction is intentionally allowed.

**Risks / follow-ups:**
- Cooldown state is in-memory only — a process restart resets both timestamps. Acceptable for MVP.
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

**Original onboarding risks / follow-ups:**
- `MW.pem` is untracked but not in `.gitignore` — worth adding to avoid accidental commits.
- Session open/close messages are Bulgarian while signal messages are English — inconsistency to address when cleaning up message formatting.
- `emul.py` has "EXPERIMENTAL" wording in Telegram messages — confirm it is never run in prod.
- Old archived log (`3rd-may-trades_log.csv`) uses different `roi_pct` scale than current code — not a bug since it's archived, but worth noting.
