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

## Phase 1 — Telegram bot MVP

- ✅ Code written and pushed: `tick.py`, `.github/workflows/tick.yml`, `data/subscribers.json`, `requirements.txt`.
- ✅ Local folder connected to `github.com/eklavyamathur9/NotiMess`, pushed to `main`.
- ✅ Bot created via @BotFather (`@NotiMessMaster_bot`), token added as the `TELEGRAM_BOT_TOKEN` GitHub Actions secret.
- ✅ Repo made public.
- ✅ **Privacy decision (2026-09-15):** subscriber data (`data/subscribers.json`) stays in the public repo as-is — considered and explicitly declined moving it to a private data repo. It only ever stores bare `chat_id`s, no names/usernames/phone numbers. See `MEMORY.md`.
- ✅ Subscribed (`/start`) and confirmed end-to-end delivery works (manually verified via `gh run view` logs on 2026-09-15 — see Phase 1.6 below for why this needed a manual nudge).
- ⬜ Spot-check `data/menus/vit_bhopal_mess_menu_september_2026.json` against the physical poster once — still outstanding.
- ⬜ Try `/settime breakfast 08:00`, `/mytimes`, `/reset` — confirm replies and that `prefs` in `data/subscribers.json` update correctly.
- ⬜ Once Phase 1.6 (below) is set up, let it run unattended for one full real day; confirm each meal notification lands within a few minutes of its (default or custom) preferred time.

## Phase 1.5 — Per-subscriber notification time (FR12, done)

- ✅ Redesigned around per-meal, per-subscriber preferred times instead of one fixed time for everyone — see `PRD.md` §22 and `ARCHITECTURE.md` §11 for the full design and the "at or after" delivery guarantee.
- ✅ Merged the old two-workflow design (`notify.yml` + `poll_subscribers.yml`) into a single `tick.py` / `tick.yml` — necessary once delivery time is per-subscriber rather than fixed, and removes a subscriber-list write race as a side benefit.
- ✅ Unit-tested locally (mocked Telegram calls): due/not-due logic, same-day dedup, `/settime` validation (rejects malformed times, accepts aliases like `hightea`), `/mytimes`, `/reset`, unknown-command help text.
- ✅ Real end-to-end verification: confirmed working via manual dispatch on 2026-09-15 (sent an overdue breakfast notification correctly once triggered).

## Phase 1.6 — Fix unreliable scheduling (found in production, 2026-09-15)

**Problem found:** GitHub's `schedule` trigger fired only 3 times in the first ~14 hours instead of the expected ~168 (every 5 min), including a 4+ hour gap that caused a missed breakfast notification and a many-hours-late welcome message. Root cause: GitHub Actions' `schedule` event runs on shared, best-effort infrastructure and is not guaranteed to fire on time — documented GitHub behavior, worse on low-activity/public repos. Full writeup in `ARCHITECTURE.md` §3.3.

**Fix:** an external scheduler (cron-job.org, free) calls GitHub's `workflow_dispatch` REST API every 1 minute instead — those dispatches aren't subject to the same throttling (confirmed: every manual test during debugging ran within ~15 seconds). `tick.yml`'s own `schedule` trigger stays as a free fallback. (Interval tightened from an initial 5-min plan to 1 min on 2026-09-15 after `/menu` — an interactive, click-and-wait command, not just a scheduled push — made the lag from a 5-min interval noticeably worse to sit through. cron-job.org's free tier supports down to 1 minute, and Actions minutes are free on this public repo, so there's no real cost to the tighter interval.)

- ✅ Root-caused via GitHub Actions run history/logs and confirmed against GitHub's documented `schedule` behavior.
- ✅ `tick.yml` already exposes `workflow_dispatch` (no code change needed — it's the same trigger used for manual testing).
- ⬜ **User action needed:** create a fine-grained GitHub PAT scoped to only `eklavyamathur9/NotiMess`, permission "Actions: Read and write" (github.com → Settings → Developer settings → Fine-grained tokens → Generate new token).
- ⬜ **User action needed:** create a free cron-job.org account, add a job:
  - URL: `https://api.github.com/repos/eklavyamathur9/NotiMess/actions/workflows/tick.yml/dispatches`
  - Method: `POST`
  - Headers: `Authorization: token <the PAT>`, `Accept: application/vnd.github+json`
  - Body: `{"ref": "main"}`
  - Schedule: every 1 minute
- ⬜ Verify: after setup, check `gh run list --repo eklavyamathur9/NotiMess` shows runs roughly every 1 minute with `event: workflow_dispatch`.

**Exit criteria:** for one full day, all four meals produce a correct, on-time Telegram notification with no manual intervention — for you as subscriber #1.

## Phase 1.7 — On-demand menu, `/menu` (FR13, done, 2026-09-15)

- ✅ `determine_target_meal()` + `build_ondemand_message()` added to `tick.py`: returns whichever meal is currently open, or the next one opening today, or tomorrow's breakfast if today's are all over.
- ✅ `/menu` command wired up, works without requiring `/start` first.
- ✅ Bot command list registered with Telegram (`setMyCommands`) so `/menu` and the others show up in the native tappable "/" picker — the "click, don't type" affordance that was asked for.
- ✅ Unit-tested locally: before-breakfast, during-breakfast, between-meals, during-lunch, and after-everything-closes-today (rolls to tomorrow) all verified correct.
- ⬜ Try it live once cron-job.org (Phase 1.6) is set up and the bot is reliably reachable.

## Phase 2 — Simple landing website

**Status: not started.** Sequencing recommendation (see chat) — finish Phase 1.6 (reliable scheduling) first; a website driving traffic to an unreliable bot would cost more trust than it builds. Once reliable, this is still a nice-to-have for discovery/credibility, not a blocker — a bare `t.me/NotiMessMaster_bot` link already works for onboarding via word of mouth / hostel group chats today.

- ⬜ One static page (see chat answer for exact scope), no backend, no login.
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
