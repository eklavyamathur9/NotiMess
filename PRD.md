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

The original Week 1 menu was extracted by Claude reading a single photo of the poster (Breakfast/High Tea high-confidence, some Lunch/Dinner cells medium-confidence) and later corrected by the user against a more careful transcription. **As of 2026-09-21, the active menu is Week 2**, supplied directly by the user as structured JSON (not photo-extracted) — different provenance, but still worth a spot-check against the physical poster since it hasn't had one yet. Note for whoever ingests the *next* update: user-supplied JSON files have arrived in a different raw shape each time (flat `breakfast`/`lunch`/... keys with a `days` sub-key, vs. the canonical `meals` wrapper with an `items` sub-key) — always convert to the canonical schema before dropping the file in `data/menus/`, don't assume the shape matches. Also check any new `(Non-Veg)`-tagged items against `strip_nonveg()`'s assumptions (§25) — Week 2 already broke one assumption Week 1 had established (see `MEMORY.md`).

## 10. Success metrics

Purely qualitative, personal-use tool — success is "notification reliably shows up 4x/day, ahead of the meal, with correct content." No formal metrics/analytics planned.

## 11. Open questions

- ~~Does the mess actually rotate through multiple weeks?~~ **Resolved 2026-09-21: yes.** Week 2 replaced Week 1 exactly 7 days after Week 1's effective date (14 Sept → 21 Sept), confirming a weekly rotation. **Not yet resolved:** whether it's a strict 2-week cycle (back to Week 1 on 28 Sept) or continues to a Week 3, and whether the cadence stays exactly 7 days going forward. One more data point (whatever menu shows up around 28 Sept) would confirm or refute a clean 2-week loop.
- **New decision point this raised:** right now, each new week's menu still requires a manual "give Claude the new file, get it swapped in" pass (this is how Week 1→2 was done) — there's no automatic rotation. Building that (a small `week` lookup keyed off days-since-anchor, per the design already sketched in `ARCHITECTURE.md` §4) was deliberately not done yet, since automating a pattern confirmed from only two data points risked locking in a wrong assumption. Worth revisiting once the cycle length is certain — see `PLAN.md` Phase 4.
- Exact cadence of menu changes beyond the weekly rotation (does the whole cycle itself get replaced monthly, each September/October etc.?) — still open, will become clearer over time.

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
- Veg-only filtering, mute weekends, choose hostel block — further per-user preferences beyond notification time, once there's demand.
- Admin web UI for menu updates (with maintainer-only login), replacing the manual Claude re-parse step.
- Multi-institution support (the `data/menus/` naming already anticipates this).

## 22. FR12 — Per-subscriber notification time

Added after V2 shipped: each subscriber can set their own preferred time per meal instead of everyone getting the same fixed time.

- **Default behaviour unchanged:** anyone who doesn't customize gets the original schedule (15 min before each counter opens — §5).
- **Customization via bot commands** (no website UI needed for this):
  - `/settime <breakfast|lunch|high_tea|dinner> <HH:MM>` — set one meal's time, 24-hour IST.
  - `/mytimes` — show current settings.
  - `/reset` — revert all four to default.
- **Delivery semantics: "at or after," not "exactly at."** The system checks on every tick whether each subscriber's preferred time for each meal has passed today and hasn't been sent yet; if so, it sends. This means actual delivery can lag the exact requested minute by roughly the tick interval (currently ~1 minute via cron-job.org, occasionally more if a dispatch is missed), but it **never double-sends and never silently skips a day** — even if a tick is delayed or missed entirely, the next one still catches anything overdue. This trade-off (small, bounded lateness vs. guaranteed eventual delivery) was chosen deliberately over trying to hit an exact minute.
- Not validated against the meal's actual counter hours (a user could set breakfast for 11 AM, after the counter closes) — the `/settime` confirmation reply includes the counter hours as a hint, but doesn't block the choice. It's the user's call.

## 23. FR13 — On-demand menu (`/menu`)

Added 2026-09-15: a way to check the menu right now, on demand, without waiting for a scheduled notification — "click a button, get the menu of whatever meal is next."

- **`/menu` command**, registered with Telegram as a tappable option (the "/" command picker next to the message box) — so it's genuinely click-to-run, not just something you have to remember to type.
- **No subscription required.** Works for anyone who messages the bot, subscribed or not — lowers the bar for someone to try it before committing to `/start`.
- **"Whatever meal is next" logic:**
  - If a meal's counter is open right now, `/menu` returns *that* meal (labeled "Currently serving").
  - Otherwise, the next meal whose counter opens later today (labeled "Coming up next").
  - If every meal for today is already over, tomorrow's breakfast (labeled "That's it for today — tomorrow's first meal") — so it never returns nothing or an error, always a useful answer.

## 24. FR14 — Full-day menu (`/full`)

Added 2026-09-15: `/full` returns all four of today's meals in a single message, for anyone who'd rather see the whole day at once than query `/menu` repeatedly. Same "no subscription required" rule as `/menu`. Respects the subscriber's veg-only preference (FR15) if they have one set.

## 25. FR15 — Veg-only filter (`/vegonly`)

Added 2026-09-15: a per-subscriber toggle that strips non-veg items out of every message they receive — scheduled notifications, `/menu`, and `/full` alike.

- **`/vegonly`** toggles the setting and confirms the new state in its reply (no separate on/off argument to remember). Requires being subscribed, since the preference has to be stored somewhere.
- **Visible in `/mytimes`**, alongside the meal times, so a subscriber can check their current setting without guessing.
- **How filtering works:** the source menu data mixes veg and non-veg options into single strings, e.g. `"Paneer Chatpata (Veg), Chicken Kosha (Non-Veg)"` (or the reverse order, e.g. `"Boiled Egg (Non-Veg) / Steamed Green Gram Sprouts (Veg)"`). When veg-only is on, each item is checked for a `(Non-Veg)` marker; if found, the item is replaced with just its veg half (tag stripped). Plain veg items (no marker at all — the majority of the menu) pass through unchanged. Verified against every such combined item in the current dataset (6 of them, in both orderings).
- **Default: off** (shows everything) for anyone who hasn't toggled it — matches the existing "customize only if you want to" pattern from notification times.
