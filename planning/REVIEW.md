# FinAlly — Review Change Log

Changes applied on 2026-04-23 based on the reviewer agent's findings.

---

## CLAUDE.md

**Problem:** Referenced two deleted files (`planning/MARKET_DATA_SUMMARY.md`, `planning/archive/`) and incorrectly stated "the market data component has been completed".

**Fix:** Removed both stale references. Updated description to say the platform is still to be developed.

---

## .claude/agents/reviewer.md

**Problem:** Broken grammar ("your check", "applivble"), mixed-up scope (plan review + competitive analysis without clear structure), `#`-commented frontmatter keys that had no effect.

**Fix:** Rewrote instructions to clearly define review scope (plan consistency, code correctness, competitive context). Fixed frontmatter (`tools`, `model` without `#`). Changed output contract: return findings as assistant message, not write to a file.

---

## planning/PLAN.md

### §5 — DB initialization wording (lazy → eager)

**Problem:** Said "backend lazily initializes the database on first request" — contradicting §8 which said "on startup (or first request)".

**Fix:** Changed to "initializes eagerly on startup". Added: `/api/health` will not return healthy until initialization completes.

### §8 — DB section heading

**Problem:** Heading said "SQLite with Lazy Initialization"; body contradicted it.

**Fix:** Renamed to "SQLite with Eager Initialization". Updated body to match.

### §8 — Schema: removed `user_id` from all tables (§14.2 decision)

**Problem:** All six tables carried a `user_id TEXT (default: "default")` column. §14.2 recommended dropping it; schema was never updated to match.

**Fix:** Removed `user_id` from every table. Updated PKs and UNIQUE constraints accordingly:

| Table | Before | After |
|---|---|---|
| `users_profile` | PK `(user_id, market)` | PK `(market)` |
| `watchlist` | UNIQUE `(user_id, market, ticker)` | UNIQUE `(market, ticker)` |
| `positions` | UNIQUE `(user_id, market, ticker)` | UNIQUE `(market, ticker)` |
| `trades` | had `user_id` column | removed |
| `portfolio_snapshots` | had `user_id` column | removed |
| `chat_messages` | had `user_id` column | removed |

Seed data rows also updated (removed `user_id="default"` from both profile rows).

Updated schema intro to say: "The schema is single-user; there is no `user_id` column (see §14.2)."

### §8 — `chat_messages.actions` clarified

**Problem:** Said "trades executed, watchlist changes made" but did not say whether `actions` stores the *proposed* set or the *executed* subset.

**Fix:** Clarified to "the subset of proposed trades/watchlist changes that were successfully executed".

### §9 — Market Movers endpoint

**Problem:** §14.1 recommended cutting Market Movers from MVP, but §9 still listed a full endpoint description as if it were in scope.

**Fix:** Replaced the description with `*(Cut from MVP — v2 stretch goal; see §14.1.)*`

### §9 — `POST /api/portfolio/trade` concurrency

**Problem:** No requirement for transactional reads/writes — two concurrent requests could both pass cash validation and overdraw the wallet.

**Fix:** Added: "Cash-balance check and position update run inside a single `BEGIN IMMEDIATE` SQLite transaction to prevent double-spend on concurrent requests."

### §9 — `GET /api/watchlist` SSR wording

**Problem:** Said "Used once on initial render / SSR hydration" — but the frontend is a static Next.js export with no runtime SSR.

**Fix:** Changed to "Fetched client-side after mount for initial render".

### §10 — LLM step 6: partial success and concurrency

**Problem:** No explicit policy on whether one invalid LLM action blocks others. No transaction requirement for multi-action chat responses.

**Fix:** Added: "Each action is evaluated independently — partial success is acceptable. Valid actions execute inside a single `BEGIN IMMEDIATE` transaction per chat response."

### §11 — Header wallet card "daily P&L"

**Problem:** Wallet card specified "daily P&L" with no definition. The SSE event has no day-baseline field, so the frontend cannot compute a true day-over-day figure for simulator tickers.

**Fix:** Clarified inline: the "daily P&L" label is cosmetic; the value is **unrealized P&L** (current mark-to-market value minus avg cost across all positions). No day baseline is needed.

### §11 — Watchlist "daily change %"

**Problem:** Same issue — "daily change %" implied a day-baseline price that doesn't exist for simulator tickers.

**Fix:** Changed to "session change %" with explicit rule: computed client-side from the first SSE price tick received for that ticker since page load (same progressive approach as sparklines).

### §11 — Market movers page bullet

**Problem:** §14.1 cut Market Movers, but §11 layout still listed it as a real panel.

**Fix:** Changed bullet to: "cut from MVP (see §14.1). V2 stretch goal."

### §14.1 — Marked decided: cut

Condensed to a one-line resolved decision. References to §9 and §11 already updated above.

### §14.2 — Marked decided: drop `user_id`

Condensed to a one-line resolved decision. Schema in §8 updated to match.

### §14.8 — Marked resolved

CLAUDE.md fix applied; §14.8 now records the resolution rather than an open recommendation.

---

## planning/Review_codex.md

Not modified. The four findings and two Q&A answers from this scratchpad have been incorporated into PLAN.md (see §9, §10, §11 changes above). You can delete this file or keep it as a working note — it is no longer the authoritative source for those decisions.
