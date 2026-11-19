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
import time
from datetime import datetime, timedelta
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
    "/menu - get the current or next meal's menu right now\n"
    "/full - get today's full menu, all four meals\n"
    "/vegonly - toggle hiding non-veg items\n"
    "/stop - unsubscribe\n"
    "/settime <breakfast|lunch|high_tea|dinner> <HH:MM> - set your own time for a meal\n"
    "/mytimes - show your current times\n"
    "/reset - reset all times back to default"
)

BOT_COMMANDS = [
    {"command": "menu", "description": "Get the current or next meal's menu right now"},
    {"command": "full", "description": "Get today's full menu, all four meals"},
    {"command": "vegonly", "description": "Toggle hiding non-veg items"},
    {"command": "start", "description": "Subscribe to meal notifications"},
    {"command": "settime", "description": "Set your own time for a meal, e.g. breakfast 08:00"},
    {"command": "mytimes", "description": "Show your current notification times"},
    {"command": "reset", "description": "Reset your times back to default"},
    {"command": "stop", "description": "Unsubscribe"},
]


# ---------- menu ----------

def parse_effective_from(value: str) -> datetime:
    cleaned = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", value)
    return datetime.strptime(cleaned, "%d %B %Y")


def load_active_menu(today: datetime) -> dict:
    candidates, loadable = [], []
    for path in MENUS_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text())
            effective = parse_effective_from(data["effective_from"])
        except (KeyError, TypeError, ValueError) as exc:
            # A new menu dropped in the wrong shape must not fail every tick;
            # warn loudly in the Actions log and keep serving the last good file.
            print(f"Skipping menu file {path.name}: {exc}", file=sys.stderr)
            continue
        loadable.append((effective, data))
        if effective.date() <= today.date():
            candidates.append((effective, data))
    pool = candidates or loadable  # nothing effective yet -> newest file anyway
    if not pool:
        raise FileNotFoundError(f"No usable menu file found in {MENUS_DIR}")
    pool.sort(key=lambda pair: pair[0])
    return pool[-1][1]


def strip_nonveg(item: str) -> str:
    """'Paneer Chatpata (Veg), Chicken Kosha (Non-Veg)' -> 'Paneer Chatpata'
    'Veg Kolapuri / Kolhapuri (Non-Veg)' -> 'Veg Kolapuri'

    Keeps whichever half of a '/'- or ','-separated pair does NOT carry a
    '(Non-Veg)' tag, then strips a '(Veg)' tag from what's kept if present.
    Doesn't require the veg half to be tagged at all -- some menu files tag
    only the non-veg alternative (its dish name alone, e.g. 'Veg Kolapuri',
    is left untouched since there's no '(Veg)' substring to strip).

    Returns '' for a non-veg item with no veg half to fall back on (a
    standalone '(Non-Veg)' dish): the whole dish is non-veg, so it is
    dropped from a veg-only menu rather than leaked into it."""
    if "(Non-Veg)" not in item:
        return item
    for sep in (" / ", ", "):
        if sep in item:
            parts = item.split(sep, 1)
            kept = [p for p in parts if "(Non-Veg)" not in p]
            if len(kept) == 1:
                return kept[0].replace("(Veg)", "").strip()
    return ""  # no veg half to keep -- drop the whole (non-veg) item


def escape_html(text: str) -> str:
    """Telegram HTML mode only allows its own tags; dish names can contain '&'."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_message(menu: dict, meal: str, today: datetime, veg_only: bool = False) -> str:
    emoji, label = MEAL_DISPLAY[meal]
    meal_data = menu["meals"].get(meal)
    weekday = today.strftime("%A")
    time_range = escape_html(meal_data["time"].replace(" to ", " – ")) if meal_data else ""
    header = f"{emoji} <b>{label}</b> — {time_range}" if meal_data else f"{emoji} <b>{label}</b>"

    items = (meal_data or {}).get("items", {}).get(weekday, [])
    if veg_only:
        items = [strip_nonveg(i) for i in items]
    items = [i for i in items if i and i.upper() != "NA"]
    body = "\n".join(f"• {escape_html(i)}" for i in items) if items else "Menu not available for today — check the noticeboard."

    return f"{header}\n\n{body}"


def parse_time_range(range_str: str):
    """'07:30 AM to 09:30 AM' -> (time(7,30), time(9,30))"""
    start_str, end_str = range_str.split(" to ")
    start = datetime.strptime(start_str.strip(), "%I:%M %p").time()
    end = datetime.strptime(end_str.strip(), "%I:%M %p").time()
    return start, end


def determine_target_meal(menu: dict, now: datetime):
    """Which meal should /menu answer with, right now?

    - If a meal's counter is open right now, that one (status "now").
    - Else the next meal whose counter opens later today (status "next").
    - Else (everything today is over) tomorrow's first meal (status "next",
      target date advanced by one day).
    """
    today_slots = []
    for meal in MEALS:
        meal_data = menu["meals"].get(meal)
        if not meal_data or not meal_data.get("time"):
            continue
        start, end = parse_time_range(meal_data["time"])
        start_dt = now.replace(hour=start.hour, minute=start.minute, second=0, microsecond=0)
        end_dt = now.replace(hour=end.hour, minute=end.minute, second=0, microsecond=0)
        today_slots.append((meal, start_dt, end_dt))

    for meal, start_dt, end_dt in today_slots:
        if start_dt <= now <= end_dt:
            return meal, now, "now"

    upcoming_today = sorted((s for s in today_slots if s[1] > now), key=lambda s: s[1])
    if upcoming_today:
        return upcoming_today[0][0], now, "next"

    return MEALS[0], now + timedelta(days=1), "next"  # everything today is over


def build_ondemand_message(menu: dict, meal: str, target_dt: datetime, status: str, now: datetime, veg_only: bool = False) -> str:
    base = build_message(menu, meal, target_dt, veg_only)
    if status == "now":
        lead = "\U0001F514 Currently serving"
    elif target_dt.date() != now.date():
        lead = "\U0001F514 That's it for today — tomorrow's first meal"
    else:
        lead = "\U0001F514 Coming up next"
    return f"{lead}:\n\n{base}"


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

def api_request(method: str, url: str, **kwargs):
    """Telegram sometimes resets the connection or times out from GitHub's
    runners. Retry those a couple of times before giving up: the tick runs
    every minute, so a transient blip should not fail the run (and email)."""
    for attempt in range(3):
        try:
            return requests.request(method, url, timeout=15, **kwargs)
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(1 + attempt)


def send(token: str, chat_id, text: str, parse_mode: str | None = None) -> dict:
    payload = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    resp = api_request(
        "POST",
        f"https://api.telegram.org/bot{token}/sendMessage",
        json=payload,
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
            subs[key] = {"prefs": dict(DEFAULT_PREFS), "last_sent": {}, "veg_only": False}
        prefs = subs[key]["prefs"]
        times = "\n".join(f"{MEAL_DISPLAY[m][0]} {MEAL_DISPLAY[m][1]}: {prefs[m]}" for m in MEALS)
        send(token, chat_id,
             "\U0001F37D️ Welcome to NotiMess!\n\n"
             "You're subscribed to VIT Bhopal hostel mess menu notifications.\n\n"
             f"Your times (defaults, IST):\n{times}\n\n"
             "Change any of them, e.g.:\n/settime breakfast 08:00\n\n"
             "/vegonly to hide non-veg items · /full for today's whole menu\n"
             "/mytimes to see your current settings · /stop to unsubscribe")

    elif cmd == "/menu":
        now = datetime.now(TIMEZONE)
        veg_only = subs.get(key, {}).get("veg_only", False)
        meal, target_dt, status = determine_target_meal(menu, now)
        send(token, chat_id, build_ondemand_message(menu, meal, target_dt, status, now, veg_only), parse_mode="HTML")

    elif cmd == "/full":
        now = datetime.now(TIMEZONE)
        veg_only = subs.get(key, {}).get("veg_only", False)
        weekday = now.strftime("%A")
        sections = [build_message(menu, m, now, veg_only) for m in MEALS]
        send(token, chat_id, f"\U0001F4C5 <b>Today's full menu</b> ({weekday}):\n\n" + "\n\n———\n\n".join(sections), parse_mode="HTML")

    elif cmd == "/vegonly":
        if key not in subs:
            send(token, chat_id, "You're not subscribed yet — send /start first.")
            return
        subs[key]["veg_only"] = not subs[key].get("veg_only", False)
        if subs[key]["veg_only"]:
            send(token, chat_id, "\U0001F331 Veg-only mode is now ON — non-veg items will be hidden from your menus.")
        else:
            send(token, chat_id, "Veg-only mode is now OFF — you'll see everything again.")

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
        veg_state = "ON" if subs[key].get("veg_only", False) else "OFF"
        send(token, chat_id, f"Your notification times (IST):\n\n{lines}\n\nVeg-only mode: {veg_state}")

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
    resp = api_request(
        "GET",
        f"https://api.telegram.org/bot{token}/getUpdates",
        params={"offset": offset, "timeout": 0},
    )
    resp.raise_for_status()
    result = resp.json()
    if not result.get("ok"):
        print(f"getUpdates failed: {result}", file=sys.stderr)
        return

    updates = result.get("result", [])
    print(f"getUpdates (offset={offset}): {len(updates)} update(s)")
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
        veg_only = sub.get("veg_only", False)
        last_sent = sub.setdefault("last_sent", {})
        for meal in MEALS:
            preferred = prefs.get(meal, DEFAULT_PREFS[meal])
            if last_sent.get(meal) == today_str:
                continue  # already sent this meal today
            if now_str < preferred:
                continue  # not due yet

            message = build_message(menu, meal, today, veg_only)
            result = send(token, int(chat_id_str), message, parse_mode="HTML")
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


def debug_bot_info(token: str) -> None:
    """One-off sanity check, cheap enough to run every tick: confirms the
    token is valid and that no webhook is registered (a webhook would make
    getUpdates return nothing, since Telegram only delivers via one channel
    at a time)."""
    try:
        me = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10).json()
        hook = requests.get(f"https://api.telegram.org/bot{token}/getWebhookInfo", timeout=10).json()
        print(f"Bot: {me.get('result', {}).get('username')!r} (ok={me.get('ok')})")
        webhook_url = hook.get("result", {}).get("url")
        print(f"Webhook URL: {webhook_url or '(none -- good, polling will work)'}")
    except requests.RequestException as exc:
        print(f"debug_bot_info failed: {exc}", file=sys.stderr)


def register_commands(token: str) -> None:
    """Registers the bot's command list with Telegram so it shows up as a
    tappable menu (the '/' icon next to the message box) -- what makes
    /menu a click-to-run option instead of something you have to type."""
    try:
        result = requests.post(
            f"https://api.telegram.org/bot{token}/setMyCommands",
            json={"commands": BOT_COMMANDS},
            timeout=10,
        ).json()
        if not result.get("ok"):
            print(f"setMyCommands failed: {result}", file=sys.stderr)
    except requests.RequestException as exc:
        print(f"register_commands failed: {exc}", file=sys.stderr)


def main() -> int:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("TELEGRAM_BOT_TOKEN is not set", file=sys.stderr)
        return 1

    debug_bot_info(token)
    register_commands(token)

    today = datetime.now(TIMEZONE)
    menu = load_active_menu(today)
    state = load_state()

    try:
        poll_updates(state, token, menu)
        blocked = send_due_notifications(state, token, menu, today)
    except requests.RequestException as exc:
        # Telegram is unreachable. The cron retries in a minute and the
        # at-or-after rule re-sends whatever was missed, so a blip is not a
        # failure. Only fail (-> one GitHub email) if it has lasted 3 ticks.
        failures = state.get("network_failures", 0) + 1
        state["network_failures"] = failures
        save_state(state)
        print(f"Telegram unreachable ({exc}); {failures} failed tick(s) in a row", file=sys.stderr)
        return 1 if failures == 3 else 0

    for chat_id_str in blocked:
        state["subscribers"].pop(chat_id_str, None)
    state["network_failures"] = 0

    save_state(state)
    print(f"Done. {len(state['subscribers'])} active subscriber(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
