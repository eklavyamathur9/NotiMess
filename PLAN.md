# NotiMess — Implementation Plan

Status key: ✅ done · ⬜ not started

## Decision update (2026-09-14): build Telegram-first, skip the solo-ntfy step

Earlier drafts of this plan had Phase 1 build a personal-only ntfy notifier first, then a separate V2 phase add multi-user Telegram delivery on top. That's now redundant: since the Telegram bot approach requires no login and no per-user setup beyond `/start`, the user can simply be subscriber #1 of their own bot — there's no need to build and later discard an ntfy-only path. **The Telegram bot *is* the V1 MVP.** The ntfy-vs-Telegram-vs-WebPush comparison in `ARCHITECTURE.md` §8 and `PRD.md` §18 still stands as the recorded reasoning for *why* Telegram was chosen; only the build order changes.

## Phase 0 — Docs & data modeling
- ✅ Define problem, requirements, notification spec → `PRD.md`
- ✅ Define system design, data model, scheduling math, delivery-channel comparison → `ARCHITECTURE.md`
- ✅ Extract menu poster into structured data → `data/menus/vit_bhopal_mess_menu_september_2026.json`
- ✅ Set up living project context doc → `MEMORY.md`
- ✅ Decide: Telegram bot for delivery, GitHub Actions for scheduling, no login for subscribers, name NotiMess

## Phase 1 — Telegram bot MVP (current focus)

Architecture simplified since first drafted — no Vercel/Upstash needed, see `ARCHITECTURE.md` §2. Only two accounts required: GitHub (have it) and Telegram.

- ✅ Code written: `notifier.py`, `poll_subscribers.py`, `.github/workflows/notify.yml`, `.github/workflows/poll_subscribers.yml`, `data/subscribers.json`, `requirements.txt`.
- ✅ Local folder connected to `github.com/eklavyamathur9/NotiMess` and pushed.
- ⬜ **User action needed:** create the bot via @BotFather on Telegram (`/newbot`), pick a name/handle, get the bot token.
- ⬜ **User action needed:** add that token as a GitHub Actions secret named `TELEGRAM_BOT_TOKEN` (exact command given in chat — keeps the token out of the conversation transcript).
- ⬜ Spot-check `data/menus/vit_bhopal_mess_menu_september_2026.json` against the physical poster once — flagged earlier, still worth a quick pass before real subscribers depend on it.
- ⬜ Subscribe to your own bot (`/start`), manually trigger `poll_subscribers.yml` via `workflow_dispatch`, confirm your `chat_id` lands in `data/subscribers.json` and you get a welcome reply.
- ⬜ Manually trigger `notify.yml` via `workflow_dispatch` once per meal type, confirm the message arrives correctly formatted.
- ⬜ Let both workflows run unattended for one full real day; confirm all 4 scheduled notifications land within ~2 minutes of target time with correct content, and that `/start`/`/stop` get picked up within ~15 minutes.

**Exit criteria:** for one full day, all four meals produce a correct, on-time Telegram notification with no manual intervention — for you as subscriber #1.

## Phase 2 — Simple landing website
Not on the critical path for Phase 1 (the bot works without it) — build once Phase 1 is stable, or in parallel if you'd rather.
- ⬜ One static page (see chat answer below for exact scope), no backend, no login.
- ⬜ Host on GitHub Pages (free, already have the repo) — simplest option since there's no server-side logic on this page at all.
- ⬜ Link the page from the bot's Telegram profile ("about" / bio), and vice versa.

## Phase 3 — Robustness
- ⬜ Implement the FR6 fallback ("menu not available") path, test it against a temporarily-empty slot.
- ⬜ Confirm GitHub's default workflow-failure email actually reaches you (trigger one deliberate failure and check).
- ⬜ Decide and document a fallback for a Telegram Bot API outage (rare, but note it in `MEMORY.md` if it ever happens).

## Phase 4 — Menu lifecycle
- ⬜ First real test of the update workflow: next time the poster changes, re-photograph → ask Claude to re-parse → update the JSON in `data/menus/` → commit. Confirm no code changes were needed.
- ⬜ If a second week's poster ever appears, confirm/deny the "Week 1/Week 2 rotation" open question from `PRD.md` and, only if confirmed, add a second dated file and the small lookup logic to pick between them.

## Phase 5 — Stretch (not committed, revisit if wanted later)
- ⬜ Per-subscriber preferences (veg-only, mute weekends, choose hostel block) — keyed on `chat_id`, no login.
- ⬜ Admin web UI for menu edits (maintainer-only login), replacing the manual Claude re-parse step.
- ⬜ WhatsApp as an additional, opt-in channel — cost-gated (see chat history for the per-message pricing breakdown), only worth it once there's real subscriber demand.
- ⬜ Multi-institution support (the `data/menus/` naming already anticipates this).
- ⬜ Explore automated OCR ingestion instead of manual Claude-assisted parsing, if menu changes become frequent enough to be worth it.

## Next concrete step
Start Phase 1: create the bot via @BotFather, then connect this folder to the GitHub repo. Say "go" when ready to start writing the actual code (bot webhook, `notifier.py`, the GitHub Actions workflow).
