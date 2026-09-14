"""
Polls Telegram for new /start and /stop messages and updates
data/subscribers.json accordingly.

Invoked by .github/workflows/poll_subscribers.yml on a short interval.
Uses long-poll-free `getUpdates` (timeout=0) since the workflow itself
provides the polling cadence -- no need to hold a connection open.
"""

import json
import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).parent
SUBSCRIBERS_FILE = ROOT / "data" / "subscribers.json"

WELCOME_TEXT = (
    "\U0001F37D️ Welcome to NotiMess!\n\n"
    "You're now subscribed to the VIT Bhopal hostel mess menu notifications "
    "-- you'll get a message about 15 minutes before each meal (breakfast, "
    "lunch, high tea, dinner) telling you what's on the menu.\n\n"
    "Send /stop anytime to unsubscribe."
)
GOODBYE_TEXT = (
    "You've been unsubscribed from NotiMess. Send /start anytime to subscribe again."
)
UNKNOWN_TEXT = "Send /start to subscribe to meal notifications, or /stop to unsubscribe."


def load_state() -> dict:
    if SUBSCRIBERS_FILE.exists():
        return json.loads(SUBSCRIBERS_FILE.read_text())
    return {"last_update_id": 0, "chat_ids": []}


def save_state(state: dict) -> None:
    SUBSCRIBERS_FILE.write_text(json.dumps(state, indent=2) + "\n")


def send_reply(token: str, chat_id: int, text: str) -> None:
    requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=15,
    )


def main() -> int:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("TELEGRAM_BOT_TOKEN is not set", file=sys.stderr)
        return 1

    state = load_state()
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
        return 1

    updates = result.get("result", [])
    if not updates:
        print("No new updates.")
        return 0

    chat_ids = set(state.get("chat_ids", []))
    max_update_id = state.get("last_update_id", 0)

    for update in updates:
        max_update_id = max(max_update_id, update["update_id"])
        message = update.get("message")
        if not message:
            continue

        chat_id = message["chat"]["id"]
        text = (message.get("text") or "").strip()

        if text.startswith("/start"):
            if chat_id not in chat_ids:
                chat_ids.add(chat_id)
                print(f"Subscribed {chat_id}")
            send_reply(token, chat_id, WELCOME_TEXT)
        elif text.startswith("/stop"):
            if chat_id in chat_ids:
                chat_ids.discard(chat_id)
                print(f"Unsubscribed {chat_id}")
            send_reply(token, chat_id, GOODBYE_TEXT)
        elif text.startswith("/"):
            send_reply(token, chat_id, UNKNOWN_TEXT)

    state["last_update_id"] = max_update_id
    state["chat_ids"] = sorted(chat_ids)
    save_state(state)
    print(f"Processed {len(updates)} update(s). {len(chat_ids)} active subscriber(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
