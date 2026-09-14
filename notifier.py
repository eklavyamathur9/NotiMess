"""
Sends the meal notification to every subscribed Telegram chat.

Invoked by .github/workflows/notify.yml, once per meal window, with the
target meal passed via the MEAL env var (breakfast|lunch|high_tea|dinner).
"""

import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).parent
MENUS_DIR = ROOT / "data" / "menus"
SUBSCRIBERS_FILE = ROOT / "data" / "subscribers.json"
TIMEZONE = ZoneInfo("Asia/Kolkata")

MEAL_DISPLAY = {
    "breakfast": ("🌅", "Breakfast"),
    "lunch": ("🍽️", "Lunch"),
    "high_tea": ("☕", "High Tea"),
    "dinner": ("🌙", "Dinner"),
}


def parse_effective_from(value: str) -> datetime:
    # "14th September 2026" -> strip the ordinal suffix, then parse.
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
        # Nothing effective yet (or effective_from is unparseable) -- fall
        # back to whatever menu file exists rather than sending nothing.
        any_file = next(MENUS_DIR.glob("*.json"), None)
        if any_file is None:
            raise FileNotFoundError(f"No menu files found in {MENUS_DIR}")
        return json.loads(any_file.read_text())
    candidates.sort(key=lambda pair: pair[0])
    return candidates[-1][1]  # most recently effective


def build_message(menu: dict, meal: str, today: datetime) -> str:
    emoji, label = MEAL_DISPLAY[meal]
    meal_data = menu["meals"].get(meal)
    weekday = today.strftime("%A")
    time_range = meal_data["time"].replace(" to ", " – ") if meal_data else ""
    header = f"{emoji} {label} — {time_range}" if meal_data else f"{emoji} {label}"

    items = (meal_data or {}).get("items", {}).get(weekday, [])
    items = [i for i in items if i and i.upper() != "NA"]

    if not items:
        body = "Menu not available for today — check the noticeboard."
    else:
        body = ", ".join(items)

    return f"{header}\n\n{body}"


def send_telegram_message(token: str, chat_id: int, text: str) -> dict:
    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=15,
    )
    return resp.json()


def main() -> int:
    meal = os.environ.get("MEAL")
    token = os.environ.get("TELEGRAM_BOT_TOKEN")

    if meal not in MEAL_DISPLAY:
        print(f"MEAL must be one of {list(MEAL_DISPLAY)}, got {meal!r}", file=sys.stderr)
        return 1
    if not token:
        print("TELEGRAM_BOT_TOKEN is not set", file=sys.stderr)
        return 1

    today = datetime.now(TIMEZONE)
    menu = load_active_menu(today)
    message = build_message(menu, meal, today)

    subscribers = json.loads(SUBSCRIBERS_FILE.read_text())
    chat_ids = subscribers.get("chat_ids", [])

    if not chat_ids:
        print("No subscribers yet -- nothing to send.")
        return 0

    blocked = []
    sent = 0
    for chat_id in chat_ids:
        result = send_telegram_message(token, chat_id, message)
        if result.get("ok"):
            sent += 1
        else:
            description = result.get("description", "")
            print(f"Failed to message {chat_id}: {description}", file=sys.stderr)
            if "blocked" in description.lower() or "chat not found" in description.lower():
                blocked.append(chat_id)
        time.sleep(0.05)  # stay well under Telegram's rate limits

    print(f"Sent {sent}/{len(chat_ids)} messages for {meal}.")

    if blocked:
        subscribers["chat_ids"] = [c for c in chat_ids if c not in blocked]
        SUBSCRIBERS_FILE.write_text(json.dumps(subscribers, indent=2) + "\n")
        print(f"Removed {len(blocked)} unreachable subscriber(s) from subscribers.json.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
