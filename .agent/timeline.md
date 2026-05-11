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

**Risks / follow-ups:**
- `MW.pem` is untracked but not in `.gitignore` — worth adding to avoid accidental commits.
- Session open/close messages are Bulgarian while signal messages are English — inconsistency to address when cleaning up message formatting.
- `emul.py` has "EXPERIMENTAL" wording in Telegram messages — confirm it is never run in prod.
- Old archived log (`3rd-may-trades_log.csv`) uses different `roi_pct` scale than current code — not a bug since it's archived, but worth noting.
