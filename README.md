# NotiMess

A Telegram bot that pushes a notification ~15 minutes before each VIT Bhopal hostel mess meal opens, listing what's being served — no need to open a menu screenshot. Anyone can subscribe with `/start`.

## How it works (short version)

1. A photo of the mess menu poster gets parsed once into `data/menus/*.json` (done interactively with Claude whenever the poster changes).
2. `tick.py` runs roughly every minute via GitHub Actions (dispatched externally by cron-job.org — GitHub's own scheduler proved too unreliable on its own, see `ARCHITECTURE.md` §3.3): it picks up any new Telegram commands, and sends each subscriber their meal notification once their own preferred time for that meal has passed (defaults apply unless customized).

No server to run, no database beyond two JSON files in this repo, no LLM call at notification time, $0 cost (the repo is public, so Actions minutes are unlimited). Full reasoning for these choices (including why Telegram over ntfy/WhatsApp/Web Push) is in `ARCHITECTURE.md`.

## Subscribe

Message the bot on Telegram. Tap the `/` icon next to the message box for a clickable command list, or type:

- `/menu` — get the current or next meal's menu right now, no subscription needed
- `/start` — subscribe (default times: Breakfast 07:15, Lunch 12:00, High Tea 16:45, Dinner 19:00 IST)
- `/settime <breakfast|lunch|high_tea|dinner> <HH:MM>` — set your own time for a meal, e.g. `/settime breakfast 08:00`
- `/mytimes` — show your current times
- `/reset` — revert all times to default
- `/stop` — unsubscribe

## Docs

- [`PRD.md`](PRD.md) — what this is, requirements, notification content spec.
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — system design, data model, scheduling math, failure handling.
- [`PLAN.md`](PLAN.md) — phased build plan and current status.
- [`MEMORY.md`](MEMORY.md) — living log of decisions and project context.

## Status

Bot is live (`@NotiMessMaster_bot`) and confirmed working end-to-end. One setup step still outstanding: GitHub's own scheduler proved unreliable at 5-minute granularity in production (see `ARCHITECTURE.md` §3.3), so an external cron (cron-job.org) needs to be pointed at the workflow — see `PLAN.md` Phase 1.6. Landing website not started yet (Phase 2).
