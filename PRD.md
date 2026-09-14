# NotiMess — Product Requirements Document

## 1. Problem

The hostel mess menu exists only as a photo of a poster stuck on a noticeboard. To find out what's being served, the user has to remember to open that photo and read a dense table — easy to forget, and mildly annoying even when remembered. There's no ambient way to know "what's for lunch today" without deliberately looking.

## 2. Goal

Get a short, readable phone notification shortly before each mess meal window opens, telling the user what's being served — with zero need to open the menu screenshot.

## 3. Non-goals (for now)

- Not a multi-user product. Built for one person (the user) initially.
- Not doing live OCR of the noticeboard photo on a schedule — menu data is parsed into structured JSON up front (by Claude, interactively) and only re-parsed when the poster changes.
- Not building a mobile app. Delivery rides on an existing notification app (ntfy).
- Not tracking mess attendance, ratings, or nutrition — purely "what's being served."

## 4. User & core story

**User:** the student living in the hostel (VIT Bhopal, Boys & Girls Hostels).

**Core story:** "As a hostel resident, 15 minutes before each meal counter opens, I want a push notification listing today's menu for that meal, so I can decide whether to go without having to look anything up."

## 5. Meal schedule (source: menu poster, Sept 2026, Week 1)

| Meal | Counter open | Counter closes | Notify at (15 min before open) |
|---|---|---|---|
| Breakfast | 07:30 AM | 09:30 AM | 07:15 AM IST |
| Lunch | 12:15 PM | 02:30 PM | 12:00 PM IST |
| High Tea | 05:00 PM | 06:30 PM | 04:45 PM IST |
| Dinner | 07:15 PM | 09:15 PM | 07:00 PM IST |

All times are `Asia/Kolkata` (IST, UTC+5:30, no DST).

## 6. Functional requirements

- **FR1 — Scheduled notification.** Fire a push notification at each of the four times above, every day, automatically, without the user's laptop or phone needing to be on/awake (delivery is push, not pull).
- **FR2 — Correct day/meal lookup.** Notification content is derived from the current IST date's day-of-week and the meal slot that's about to open, read from a structured menu dataset (`data/menus/*.json`).
- **FR3 — Readable content.** Message is short enough to read in a lockscreen preview (title = meal name + time window, body = comma-separated dish list, veg/non-veg markers preserved).
- **FR4 — Menu update workflow.** When the mess menu poster changes (new month, new week rotation), the user re-photographs it and asks Claude to re-parse it into `data/menus/*.json`; no code changes needed for a pure data update.
- **FR5 — Manual trigger.** Able to manually fire a test notification on demand (to verify delivery works, or check "what's next meal" outside the schedule) via a manual GitHub Actions run.
- **FR6 — No missed-meal silence.** If a meal's item list is empty/missing in the data, still send a "menu not available" notification rather than silently skipping — so the absence of food info is itself visible, not indistinguishable from "no notification arrived at all."

## 7. Non-functional requirements

- **Cost:** $0. Both ntfy.sh and GitHub Actions free tiers are sufficient at 4 runs/day.
- **Reliability:** should not depend on a personal device being powered on. GitHub Actions cron + ntfy push satisfies this.
- **Latency:** notification should land within ~2 minutes of the scheduled fire time (GitHub Actions cron has inherent scheduling jitter of a few minutes — acceptable given a 15-minute lead time buffer).
- **Privacy:** menu content isn't sensitive, but the ntfy topic name should be an unguessable string (acts as the only access control on a public ntfy.sh server) since anyone who knows the topic name can read/publish to it.
- **Maintainability:** a single person maintains this; prioritize simplicity (flat JSON + one script) over extensibility.

## 8. Notification content spec

- **Title:** `🍽️ Lunch — 12:15–2:30 PM`
- **Body:** `Roti, Plain Rice, Dal Fry, Aloo Gobi Masala Dry, Sambar, Beans Patani Poriyal, Pepper Rasam, Curd, Kheer, Pickle`
- Emoji per meal: 🌅 Breakfast, 🍽️ Lunch, ☕ High Tea, 🌙 Dinner.

## 9. Data quality caveat

The current `data/menus/*.json` was extracted by Claude reading a single photo of the poster. Breakfast and High Tea rows are high-confidence; some Lunch/Dinner cells (particularly Saturday/Sunday) were reconstructed from a densely merged table and carry medium confidence — see `_extraction_meta` in the JSON file. **Action item:** spot-check against the physical poster once during Phase 1 (see `PLAN.md`).

## 10. Success metrics

Purely qualitative, personal-use tool — success is "notification reliably shows up 4x/day, ahead of the meal, with correct content." No formal metrics/analytics planned.

## 11. Open questions

- Does the mess actually rotate through multiple weeks (poster says "Week 1"), or was that just how September's single menu happens to be labeled? Unknown until a Week 2 poster is seen. `data/menus/*.json` currently only encodes one week and is treated as a repeating 7-day cycle until proven otherwise.
- Exact cadence of menu changes (monthly?) — determines how often the re-ingestion workflow (FR4) actually gets exercised.

## 12. Future ideas (explicitly out of scope for v1)

- Multi-week rotation support once a second week's poster is available.
- "Skip today" / mute controls (e.g., while traveling).
- Support for a second user/mess hall by parameterizing the data source.
- Auto re-ingestion via OCR instead of manual Claude-assisted parsing.

---

# Part 2 — V2: Multi-user platform

## 13. Problem (V2)

V1 solves this for one person. Other VIT Bhopal hostel students have the exact same problem — the menu only exists as a noticeboard photo, and everyone independently forgets to check it. Turning NotiMess into something anyone can subscribe to solves it once for everyone instead of once per person re-inventing it.

## 14. Goal (V2)

A public, self-serve way for any student to start receiving the same 4x/day meal notifications, with a lightweight website as the front door.

## 15. Non-goals (V2)

- Not building a native mobile app.
- Not requiring an account/login to receive notifications (see §17 — explicit decision).
- Not supporting institutions beyond VIT Bhopal's Boys & Girls Hostels menu yet — the data model already keys menus by institution+month (`data/menus/`), so this is a config change later, not a rebuild, but it isn't being built speculatively now.
- Not monetizing. Free tool, free-tier infra only.

## 16. Functional requirements (V2, additive to §6)

- **FR7 — Self-serve subscribe.** Any student can start receiving notifications without asking the maintainer to add them manually.
- **FR8 — Self-serve unsubscribe.** Equally easy to stop.
- **FR9 — One data pipeline, many recipients.** The existing menu-lookup/formatting logic (`notifier.py` from V1) is reused as-is; only the "send to whom" step changes from one hardcoded ntfy topic to a list of subscribers.
- **FR10 — Landing page.** A simple public webpage explaining what NotiMess is and how to subscribe (see §18 for what it does *not* need to be).
- **FR11 — No end-user login.** Subscribing/unsubscribing never requires creating a username/password account.

## 17. Decision: should the website require login?

**No.** Recommendation, and reasoning:

- There is no private, per-user data involved — the thing being delivered (mess menu) is the same for every subscriber and isn't sensitive.
- A login system (signup, password storage/hashing, session management, password reset flows) is real engineering and real security surface for a free utility that has nothing to protect. The risk/effort isn't justified by the benefit.
- The chosen delivery channel (see §18) already provides a lightweight, free identity: a Telegram `chat_id` is enough to know who to message and to let someone unsubscribe (block the bot / `/stop`), without NotiMess ever handling a password.
- If personalization is added later (e.g. "only notify me for veg items," "mute weekends," "pick your hostel block"), that's solved by storing preferences keyed on the *existing* channel identity (chat_id) — not by bolting on a full account system. Where a magic-link/OTP is ever needed for that, it's still passwordless.
- The one place a login genuinely earns its keep: an **admin-only** menu-management screen for the maintainer(s), gated separately from the public subscribe flow (e.g. GitHub OAuth or a shared secret) — and even that is a "future ideas" item (§21), not required for V2 MVP, since menu updates already work fine via the V1 "re-photograph → Claude re-parses" workflow.

## 18. Decision: delivery channel

Three options were weighed (full comparison in `ARCHITECTURE.md` §8):

1. **Shared public ntfy.sh topic** — zero backend, but no spoofing protection (anyone who learns the topic name can send fake notices to every subscriber) and no way to track/manage subscribers.
2. **Telegram bot** — *recommended.* No app-store presence needed, near-universal among students already, free Bot API, `chat_id` doubles as both identity and delivery address, small backend (one serverless function + a small subscriber store).
3. **Web Push via a PWA** — most "own-brand" experience, but meaningfully more engineering (VAPID keys, service worker, a persistent backend, database) and iOS support is limited to 16.4+ with the site added to the home screen. Reasonable *future* upgrade once there's real demand, not the V2 MVP.

**V2 is built around the Telegram bot.** The website's role shrinks to a landing page that explains the project and links to "Start the bot."

## 19. Notification content (V2)

Unchanged from §8 — same message, just sent to many `chat_id`s instead of one ntfy topic.

## 20. Success metrics (V2)

Still informal, but now meaningful: number of active subscribers (chat_ids that haven't blocked the bot), and whether notifications keep landing reliably as subscriber count grows (Telegram Bot API easily handles a few thousand sends within its rate limits — not a real concern at hostel scale).

## 21. Future ideas (V2, explicitly out of scope for now)

- Web Push/PWA as an alternative channel for students who don't use Telegram.
- Per-user preferences (veg-only, mute weekends, choose hostel block) once there's demand — passwordless, keyed on chat_id.
- Admin web UI for menu updates (with maintainer-only login), replacing the manual Claude re-parse step.
- Multi-institution support (the `data/menus/` naming already anticipates this).
