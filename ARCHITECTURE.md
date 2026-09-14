# NotiMess — Architecture

## 1. Overview

NotiMess is deliberately a **static-data + scheduled-script** system, not a live service. There's no server to keep running, no database beyond the repo itself, and no LLM call anywhere in the runtime path. The only "smart" step (reading the menu poster photo) happens once, offline, interactively with Claude — its output is a plain JSON file committed to the repo. Everything that runs on a schedule afterwards is small, dumb, and fast.

**Delivery channel: Telegram bot.** Chosen over a shared ntfy topic (no spoofing protection) and Web Push/PWA (needs a real backend + database + iOS limitations) — full comparison in §8. Since a Telegram bot needs no login and no per-user setup beyond `/start`, it serves both the original "notify me" goal and the "let anyone subscribe" goal at once — there's no separate personal-only build.

```mermaid
flowchart LR
    subgraph "One-time / occasional, whenever the poster changes"
        A[Photo of mess<br/>noticeboard poster] -->|Claude reads image,<br/>extracts structured data| B[data/menus/*.json]
    end

    subgraph "Every ~5 min, unattended"
        C[GitHub Actions<br/>tick.yml] --> D[tick.py]
        B --> D
        D <-->|getUpdates / sendMessage| TG[Telegram Bot API]
        D -->|read + write,<br/>commit if changed| S[data/subscribers.json]
    end

    TG -->|push, per subscriber's<br/>own preferred time| U[Student's phone]
```

## 2. Why no external services beyond GitHub + Telegram

An earlier draft of this architecture planned a webhook-based design: a serverless function (Vercel/Cloudflare) receiving Telegram's `/start` events in real time, backed by a key-value store (Upstash Redis) for the subscriber list. That works, but it means creating and maintaining two more third-party accounts for what is, functionally, a list of chat IDs.

**Simplification adopted:** Telegram's Bot API supports *polling* (`getUpdates`) as well as webhooks — a client can just ask "any new messages since last time?" instead of needing a public HTTPS endpoint to receive pushes. So instead of a webhook function + Redis, GitHub Actions polls on a schedule, and the subscriber list is a JSON file **committed to the repo itself**, exactly like the menu data. This means:

- Only two accounts needed, total: GitHub (already have) and Telegram (bot via @BotFather).
- No new hosting platform, no database service, no secrets to manage outside GitHub Actions secrets.
- The tick workflow commits to the repo only on runs where something actually changed (a new subscriber, a preference change, a notification sent), which is a little unconventional but keeps everything in one place and auditable via git history.

**Further simplification (added with per-subscriber notification times, §11):** originally this was two separate workflows — a 4x/day `notify.yml` sending at fixed times, and a ~15-min `poll_subscribers.yml` capturing `/start`/`/stop`. Once each subscriber can pick their *own* time per meal, "send at a fixed time" no longer makes sense — the system instead needs to check frequently whether *anyone's* preferred time has just passed. That check has to run often anyway, so polling for new Telegram messages was folded into the same run: **one script (`tick.py`), one workflow (`tick.yml`), every ~5 minutes.** This also removes a subtle risk the two-workflow design had — two independently-scheduled jobs writing to the same `data/subscribers.json` — since there's now only ever one writer.

## 3. Components

### 3.1 Menu data store — `data/menus/*.json`
- Single source of truth for what's being served.
- Structure: meal-major. Top-level `meals` object keyed by `breakfast`/`lunch`/`high_tea`/`dinner`, each carrying its time window (`time`, `counter_closing_time`) and an `items` object keyed by day name (`"Monday"`..`"Sunday"`) → flat list of dish strings. One file per institution+month (e.g. `vit_bhopal_mess_menu_september_2026.json`).
- Treated as **read-only by the scheduled jobs** — it only ever gets updated by a human (with Claude's help) re-parsing a new poster photo.
- The current file was corrected once already (see `MEMORY.md` change log, 2026-09-14) after a user-supplied re-transcription fixed several cells an earlier automated pass got wrong — a concrete reminder that a fresh poster photo should always be spot-checked, not just trusted from a single vision pass.

### 3.2 Subscriber store — `data/subscribers.json`
- Flat JSON array of Telegram `chat_id`s (numbers). Grows to `[{"chat_id": ..., "joined_at": ...}]` if/when per-subscriber preferences are ever added — not needed yet.
- Owned exclusively by `poll_subscribers.py` (below) — `notifier.py` only ever reads it.
- Committed to the repo by the poll workflow using the built-in `GITHUB_TOKEN` (no extra credential needed).

### 3.3 Scheduler — GitHub Actions (`.github/workflows/tick.yml`)
- Chosen over local cron because it doesn't depend on any personal device being powered on (reliability requirement).
- Single `schedule` cron, `*/5 * * * *` (every 5 minutes), plus `workflow_dispatch` for manual testing.
- `concurrency: { group: notimess-tick, cancel-in-progress: false }` so overlapping runs queue instead of clashing if a run ever takes longer than the 5-minute interval.
- Public repo → GitHub Actions minutes are unlimited on standard runners, so the 5-minute cadence (≈288 runs/day) costs nothing. (This wasn't true while the repo was private — the free tier there is 2,000 min/month, which this cadence would have threatened.)
- GitHub Actions cron has a documented jitter under load; combined with the "at or after" delivery semantics in §11, a delayed or even occasionally-skipped tick just means slightly late delivery, never a missed day.

### 3.4 Tick script — `tick.py`
Runtime logic, no external LLM/API dependency. One run does both of:
1. **Poll for new messages:** call Telegram's `getUpdates` with an `offset` past the last-seen update ID (persisted in `data/subscribers.json` so nothing is double-processed). Route any `/start`, `/stop`, `/settime`, `/mytimes`, `/reset` command to its handler (§11).
2. **Check and send due notifications:** for every subscriber, for every meal, compare their preferred time (default or custom) against the current `Asia/Kolkata` time; if it's passed and today's notification for that meal hasn't been sent yet, build the message (menu lookup + format per `PRD.md` §8) and send it via `sendMessage`.
3. If a `sendMessage` call comes back "blocked"/"chat not found," drop that subscriber — no point retrying someone who's blocked the bot.
4. Save `data/subscribers.json` if anything changed; the workflow step commits it.

Kept to a single file, stdlib + `requests` only — no framework needed for something this small.

### 3.5 Delivery — Telegram Bot API
- Bot created once via `@BotFather`, token stored as a GitHub Actions secret (`TELEGRAM_BOT_TOKEN`) — never committed to the repo.
- No account needed on the subscriber's end beyond Telegram itself, which the target audience already has.
- `chat_id` doubles as both the delivery address and the only "identity" NotiMess ever stores about a subscriber.

## 4. Data model

**Menu (`data/menus/*.json`):**
```jsonc
{
  "institution": "VIT Bhopal",
  "effective_from": "14th September 2026",
  "week": 1,
  "days": ["Monday", "Tuesday", "...", "Sunday"],
  "meals": {
    "breakfast": {
      "time": "07:30 AM to 09:30 AM",
      "counter_closing_time": "09:30 AM",
      "items": {
        "Monday": ["Idly", "Moong Dhal Sambar", "..."],
        "...": ["..."]
      }
    }
    // ... lunch, high_tea, dinner, same shape
  },
  "notes": ["..."]
}
```

**Subscribers (`data/subscribers.json`):**
```jsonc
{
  "last_update_id": 123456789,
  "subscribers": {
    "111111111": {
      "prefs": { "breakfast": "07:15", "lunch": "12:00", "high_tea": "16:45", "dinner": "19:00" },
      "last_sent": { "breakfast": "2026-09-18", "lunch": "2026-09-18" }
    }
  }
}
```

Design choices:
- **Flat string lists per day** in the menu — the notification just joins them with commas; the poster's own categorization doesn't need to survive into the message.
- **Meal-major, day-minor** (`meals.lunch.items.Monday`) — matches how the source poster itself is laid out.
- **One repeating 7-day cycle**, not a calendar of specific dates. If a genuine multi-week rotation is confirmed later (open question in `PRD.md`), a second dated file (`..._week2.json`) is the natural extension.
- **One file per institution+month** under `data/menus/` — a month-to-month menu change or a future second institution is just "add another file," never a schema change.
- **Subscribers as one JSON object in one file**, keyed by `chat_id` (string, since JSON object keys must be strings) — not a per-user file or external DB. At hostel scale (hundreds, maybe low thousands of subscribers) this is plenty, and it keeps the "no external services" property intact.
- **`prefs` (per-meal preferred time) and `last_sent` (per-meal last-sent date) live together per subscriber** — see §11 for why `last_sent` is needed (it's what makes the "check every 5 min, send once per day" model correct: it's the dedup key that stops a subscriber getting the same meal's notification on every tick after their preferred time has passed).
- Canonical time strings are always zero-padded 24-hour `HH:MM` (`08:00`, not `8:0` or `8:00`) specifically so they can be **string-compared** directly against `datetime.strftime("%H:%M")` without parsing — one less thing that can go subtly wrong.

## 5. Menu update workflow (when the poster changes)

1. User photographs the new poster, drops it in the project directory.
2. User asks Claude (in this project) to re-parse it.
3. Claude reads the image, updates/adds the file in `data/menus/`.
4. Commit + push. Next tick picks up the new data automatically — no script/workflow changes needed for a pure menu content update.

## 6. Failure modes & handling

| Failure | Handling |
|---|---|
| `tick.yml` run fails (script error, Telegram API down) | GitHub emails the repo owner on workflow failure by default — free monitoring signal. |
| Telegram Bot API itself is down | Out of scope to mitigate for a free personal/community tool; the next successful tick catches anything overdue (§11) — no permanent miss, just delay. |
| Menu JSON missing/malformed data for a slot | Script sends an explicit "menu not available" message instead of failing silently (FR6). |
| A tick is skipped or delayed (GitHub Actions outage/jitter) | Self-healing by design: `last_sent` means the next tick still sends anything that became due since the last successful run — see §11. |
| Two tick runs try to commit `data/subscribers.json` at once | Prevented structurally — `concurrency: cancel-in-progress: false` in `tick.yml` means only one run executes at a time; a `git pull --rebase` before push is a cheap extra safety net. |
| Poster's menu rotates on a cycle we don't know about | Flagged as an open question in `PRD.md`; not solvable until a second week's poster is observed. |

## 7. Tech stack

- **Language:** Python 3 (stdlib `json`, `datetime`/`zoneinfo`, `re`, plus `requests` for HTTP calls to the Telegram Bot API).
- **Scheduler/runtime:** GitHub Actions (`schedule` + `workflow_dispatch` triggers, one workflow).
- **Delivery:** Telegram Bot API (`sendMessage`, `getUpdates`).
- **Storage:** two JSON files in the repo (menu data, subscriber list) — no database, no external services.

## 8. Delivery channel comparison (recorded reasoning)

| | Shared ntfy topic | **Telegram bot (chosen)** | Web Push / PWA |
|---|---|---|---|
| App install needed | ntfy app | Telegram (near-universal already) | None (browser) |
| Backend needed | None | None (GitHub Actions polling — see §2) | DB + service worker + VAPID |
| Identity/auth | None (topic name = weak secret) | `chat_id` (free, built-in) | Push subscription object (free, built-in) |
| Spoofing risk | High — anyone with the topic name can publish to all subscribers | Low — only the bot (holds the token) can send | Low |
| iOS support | Full (native app) | Full (native app) | Limited — 16.4+, must Add to Home Screen |
| Effort to build | Lowest | Low | Highest |
| Ongoing cost | $0 | $0 | $0 (but more infra to maintain) |

WhatsApp Business API was also evaluated and ruled out on cost/complexity grounds — see `MEMORY.md` for the pricing breakdown (₹0.115–0.86 per message in India, no free tier for our proactive-message use case, plus business verification overhead).

## 9. Landing website

A static page, no login, no backend of its own — see `PLAN.md` Phase 2. Hosted on GitHub Pages. Its job is discovery/trust (explains the project, links to `t.me/<BotUsername>`), optionally showing a read of today's menu pulled from `data/menus/*.json`. It is not part of the notification delivery path.

## 10. Directory structure

```
NotiMess/
├── README.md
├── PRD.md
├── ARCHITECTURE.md
├── MEMORY.md
├── PLAN.md
├── menu.jpeg                              # source photo (Week 1, Sept 2026)
├── requirements.txt
├── tick.py                                # poll Telegram + send due notifications, one pass
├── data/
│   ├── menus/
│   │   └── vit_bhopal_mess_menu_september_2026.json
│   └── subscribers.json
└── .github/
    └── workflows/
        └── tick.yml                       # every 5 min → tick.py
```

## 11. Per-subscriber notification time (FR12)

Each subscriber can set their own preferred delivery time per meal instead of a fixed time everyone shares.

- **Commands** (handled in `tick.py`, no website UI involved): `/settime <meal> <HH:MM>`, `/mytimes`, `/reset`. Full spec and copy in `PRD.md` §22.
- **Storage:** each subscriber's `prefs` dict holds their four meal times (defaulting to the original fixed schedule — §3.3's old times — until customized), and a `last_sent` dict holds the date each meal was last delivered.
- **Delivery rule, run every tick (~5 min):** for each subscriber × meal, send if `now (HH:MM) >= prefs[meal]` **and** `last_sent[meal] != today's date`; on send, set `last_sent[meal] = today`.
- **Why "at or after" instead of "at exactly":** trying to match an exact 5-minute tick to an arbitrary user-chosen minute would mean most preferred times get silently missed (e.g. a 5-minute tick grid can't land exactly on `:07`). The "at or after, once per day" rule instead guarantees exactly one send per meal per day, arriving within one tick interval *after* the requested time — never early, never skipped, self-healing if a tick is delayed. The bounded lateness (typically under 5 minutes, occasionally more under GitHub Actions load) was judged an acceptable trade for that guarantee.
- **Not validated against counter hours:** a subscriber can set a meal's time to something after that counter actually closes. `/settime`'s confirmation reply includes the counter hours as a hint; the system doesn't block the choice.
