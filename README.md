# NotiMess

A Telegram bot that pushes a notification ~15 minutes before each VIT Bhopal hostel mess meal opens, listing what's being served — no need to open a menu screenshot. Anyone can subscribe with `/start`.

## How it works (short version)

1. A photo of the mess menu poster gets parsed once into `data/menus/*.json` (done interactively with Claude whenever the poster changes).
2. `poll_subscribers.py` runs every ~15 minutes via GitHub Actions, picking up `/start`/`/stop` messages sent to the bot and keeping `data/subscribers.json` up to date.
3. `notifier.py` runs 4x/day via GitHub Actions (before breakfast, lunch, high tea, dinner), reads that day's menu, and messages every subscribed chat via the Telegram Bot API.

No server to run, no database beyond two JSON files in this repo, no LLM call at notification time, $0 cost. Full reasoning for these choices (including why Telegram over ntfy/WhatsApp/Web Push) is in `ARCHITECTURE.md`.

## Subscribe

Message [`@YourBotHandle`](https://t.me/) on Telegram (handle TBD once created — see `PLAN.md`) and send `/start`. Send `/stop` anytime to unsubscribe.

## Docs

- [`PRD.md`](PRD.md) — what this is, requirements, notification content spec.
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — system design, data model, scheduling math, failure handling.
- [`PLAN.md`](PLAN.md) — phased build plan and current status.
- [`MEMORY.md`](MEMORY.md) — living log of decisions and project context.

## Status

Phase 1 (Telegram bot MVP) code is written. Still needed before it's live: create the bot via @BotFather and add its token as a GitHub Actions secret — see `PLAN.md`.
