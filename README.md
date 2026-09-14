# NotiMess

A Telegram bot that pushes a notification ~15 minutes before each VIT Bhopal hostel mess meal opens, listing what's being served — no need to open a menu screenshot. Anyone can subscribe with `/start`.

## How it works (short version)

1. A photo of the mess menu poster gets parsed once into `data/menus/*.json` (done interactively with Claude whenever the poster changes).
2. `tick.py` runs every ~5 minutes via GitHub Actions: it picks up any new Telegram commands, and sends each subscriber their meal notification once their own preferred time for that meal has passed (defaults apply unless customized).

No server to run, no database beyond two JSON files in this repo, no LLM call at notification time, $0 cost (the repo is public, so Actions minutes are unlimited). Full reasoning for these choices (including why Telegram over ntfy/WhatsApp/Web Push) is in `ARCHITECTURE.md`.

## Subscribe

Message the bot on Telegram and send `/start`. Commands:

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

Phase 1 (Telegram bot MVP) code is written. Still needed before it's live: create the bot via @BotFather and add its token as a GitHub Actions secret — see `PLAN.md`.
