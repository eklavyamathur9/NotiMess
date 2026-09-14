"""
Runs every ~5 minutes via .github/workflows/tick.yml. Does two things in
one pass, writing data/subscribers.json at most once:

  1. Polls Telegram for new messages (/start, /stop, /settime, /mytimes,
     /reset) and applies them to the subscriber store.
  2. Checks every subscriber's per-meal preferred time against the current
     IST time and sends any meal notification that's newly due today.

Replaces the earlier notifier.py + poll_subscribers.py split: merging them
means there's only ever one writer of subscribers.json (no race between
two separately-scheduled workflows), and "per-subscriber preferred time"
needs frequent due-checks anyway, which naturally also covers polling.
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).parent
MENUS_DIR = ROOT / "data" / "menus"
SUBSCRIBERS_FILE = ROOT / "data" / "subscribers.json"
TIMEZONE = ZoneInfo("Asia/Kolkata")

MEALS = ["breakfast", "lunch", "high_tea", "dinner"]
MEAL_ALIASES = {
    "breakfast": "breakfast", "bf": "breakfast",
    "lunch": "lunch",
    "hightea": "high_tea", "high_tea": "high_tea", "tea": "high_tea", "high-tea": "high_tea",
    "dinner": "dinner",
}
DEFAULT_PREFS = {"breakfast": "07:15", "lunch": "12:00", "high_tea": "16:45", "dinner": "19:00"}
MEAL_DISPLAY = {
    "breakfast": ("\U0001F305", "Breakfast"),
    "lunch": ("\U0001F37D️", "Lunch"),
    "high_tea": ("☕", "High Tea"),
    "dinner": ("\U0001F319", "Dinner"),
}
TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")

HELP_TEXT = (
    "Commands:\n"
    "/start - subscribe (uses default times below)\n"
    "/stop - unsubscribe\n"
    "/settime <breakfast|lunch|high_tea|dinner> <HH:MM> - set your own time for a meal\n"
    "/mytimes - show your current times\n"
    "/reset - reset all times back to default"
)


# ---------- menu ----------

def parse_effective_from(value: str) -> datetime:
    cleaned = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", value)
    return datetime.strptime(cleaned, "%d %B %Y")


def load_active_menu(today: datetime) -> dict:
    candidates = []
    for path in MENUS_DIR.glob("*.json"):
        data = json.loads(path.read_text())
        effective = parse_effective_from(data["effective_from"])
        if effective.date() <= today.date():
            candidates.append((effective, data))
    if not candidates:
        any_file = next(MENUS_DIR.glob("*.json"), None)
        if any_file is None:
            raise FileNotFoundError(f"No menu files found in {MENUS_DIR}")
        return json.loads(any_file.read_text())
    candidates.sort(key=lambda pair: pair[0])
    return candidates[-1][1]


def build_message(menu: dict, meal: str, today: datetime) -> str:
    emoji, label = MEAL_DISPLAY[meal]
    meal_data = menu["meals"].get(meal)
    weekday = today.strftime("%A")
    time_range = meal_data["time"].replace(" to ", " – ") if meal_data else ""
    header = f"{emoji} {label} — {time_range}" if meal_data else f"{emoji} {label}"

    items = (meal_data or {}).get("items", {}).get(weekday, [])
    items = [i for i in items if i and i.upper() != "NA"]
    body = ", ".join(items) if items else "Menu not available for today — check the noticeboard."

    return f"{header}\n\n{body}"


# ---------- subscriber store ----------

def load_state() -> dict:
    if SUBSCRIBERS_FILE.exists():
        data = json.loads(SUBSCRIBERS_FILE.read_text())
        if "subscribers" in data:
            return data
    # Fresh file, or the pre-preferences schema {"last_update_id", "chat_ids"} -- nothing to
    # migrate in practice (checked before this change shipped: no real subscribers existed yet).
    return {"last_update_id": 0, "subscribers": {}}


def save_state(state: dict) -> None:
    SUBSCRIBERS_FILE.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


# ---------- Telegram ----------

def send(token: str, chat_id, text: str) -> dict:
    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=15,
    )
    return resp.json()


def parse_time(raw: str):
    m = TIME_RE.match(raw)
    if not m:
        return None
    hour, minute = int(m.group(1)), int(m.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return f"{hour:02d}:{minute:02d}"  # canonical, zero-padded -- safe to string-compare


def handle_command(state: dict, token: str, chat_id: int, text: str, menu: dict) -> None:
    subs = state["subscribers"]
    key = str(chat_id)
    parts = text.split()
    cmd = parts[0].lower().split("@")[0]  # strip a possible @BotName suffix

    if cmd == "/start":
        if key not in subs:
            subs[key] = {"prefs": dict(DEFAULT_PREFS), "last_sent": {}}
        prefs = subs[key]["prefs"]
        times = "\n".join(f"{MEAL_DISPLAY[m][0]} {MEAL_DISPLAY[m][1]}: {prefs[m]}" for m in MEALS)
        send(token, chat_id,
             "\U0001F37D️ Welcome to NotiMess!\n\n"
             "You're subscribed to VIT Bhopal hostel mess menu notifications.\n\n"
             f"Your times (defaults, IST):\n{times}\n\n"
             "Change any of them, e.g.:\n/settime breakfast 08:00\n\n"
             "/mytimes to see your current settings · /stop to unsubscribe")

    elif cmd == "/stop":
        if key in subs:
            del subs[key]
        send(token, chat_id, "You've been unsubscribed from NotiMess. Send /start anytime to subscribe again.")

    elif cmd == "/settime":
        if key not in subs:
            send(token, chat_id, "You're not subscribed yet — send /start first.")
            return
        if len(parts) != 3:
            send(token, chat_id, "Usage: /settime <breakfast|lunch|high_tea|dinner> <HH:MM>\nExample: /settime breakfast 08:00")
            return
        meal = MEAL_ALIASES.get(parts[1].lower())
        time_str = parse_time(parts[2])
        if not meal:
            send(token, chat_id, "Unknown meal. Use one of: breakfast, lunch, high_tea, dinner")
            return
        if not time_str:
            send(token, chat_id, "Time must be 24-hour HH:MM, e.g. 08:00 or 19:30")
            return
        subs[key]["prefs"][meal] = time_str
        emoji, label = MEAL_DISPLAY[meal]
        counter = menu["meals"].get(meal, {}).get("time", "") if menu else ""
        note = f"\n(Counter hours: {counter})" if counter else ""
        send(token, chat_id, f"Done — {label} notifications now arrive at {time_str} IST.{note}")

    elif cmd == "/mytimes":
        if key not in subs:
            send(token, chat_id, "You're not subscribed — send /start first.")
            return
        prefs = subs[key]["prefs"]
        lines = "\n".join(f"{MEAL_DISPLAY[m][0]} {MEAL_DISPLAY[m][1]}: {prefs.get(m, DEFAULT_PREFS[m])}" for m in MEALS)
        send(token, chat_id, f"Your notification times (IST):\n\n{lines}")

    elif cmd == "/reset":
        if key in subs:
            subs[key]["prefs"] = dict(DEFAULT_PREFS)
            send(token, chat_id, "Times reset to default.")
        else:
            send(token, chat_id, "You're not subscribed — send /start first.")

    else:
        send(token, chat_id, HELP_TEXT)


def poll_updates(state: dict, token: str, menu: dict) -> None:
    offset = state.get("last_update_id", 0) + 1
    resp = requests.get(
        f"https://api.telegram.org/bot{token}/getUpdates",
        params={"offset": offset, "timeout": 0},
        timeout=15,
    )
    resp.raise_for_status()
    result = resp.json()
    if not result.get("ok"):
        print(f"getUpdates failed: {result}", file=sys.stderr)
        return

    updates = result.get("result", [])
    if not updates:
        return

    max_update_id = state.get("last_update_id", 0)
    for update in updates:
        max_update_id = max(max_update_id, update["update_id"])
        message = update.get("message")
        if not message:
            continue
        text = (message.get("text") or "").strip()
        if text.startswith("/"):
            handle_command(state, token, message["chat"]["id"], text, menu)

    state["last_update_id"] = max_update_id


def send_due_notifications(state: dict, token: str, menu: dict, today: datetime) -> list:
    today_str = today.strftime("%Y-%m-%d")
    now_str = today.strftime("%H:%M")
    blocked = []

    for chat_id_str, sub in state["subscribers"].items():
        prefs = sub.get("prefs", DEFAULT_PREFS)
        last_sent = sub.setdefault("last_sent", {})
        for meal in MEALS:
            preferred = prefs.get(meal, DEFAULT_PREFS[meal])
            if last_sent.get(meal) == today_str:
                continue  # already sent this meal today
            if now_str < preferred:
                continue  # not due yet

            message = build_message(menu, meal, today)
            result = send(token, int(chat_id_str), message)
            if result.get("ok"):
                last_sent[meal] = today_str
                print(f"Sent {meal} to {chat_id_str} (preferred {preferred}, sent at {now_str})")
            else:
                description = result.get("description", "")
                print(f"Failed to message {chat_id_str} for {meal}: {description}", file=sys.stderr)
                if "blocked" in description.lower() or "chat not found" in description.lower():
                    blocked.append(chat_id_str)
                    break  # stop trying this subscriber's other meals this run

    return blocked


def main() -> int:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("TELEGRAM_BOT_TOKEN is not set", file=sys.stderr)
        return 1

    today = datetime.now(TIMEZONE)
    menu = load_active_menu(today)
    state = load_state()

    poll_updates(state, token, menu)
    blocked = send_due_notifications(state, token, menu, today)
    for chat_id_str in blocked:
        state["subscribers"].pop(chat_id_str, None)

    save_state(state)
    print(f"Done. {len(state['subscribers'])} active subscriber(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
