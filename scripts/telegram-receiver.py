
#!/usr/bin/env python3
"""Telegram text-to-Hugo publisher for SpykeSpace."""

import getpass
import json
import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRANSMISSIONS = ROOT / "content" / "transmissions"
AUTHORIZED_USER = 8476369874
POLL_SECONDS = 20


def telegram(token, method, params=None):
    url = f"https://api.telegram.org/bot{token}/{method}"
    payload = urllib.parse.urlencode(params or {}).encode()
    request = urllib.request.Request(url, data=payload)
    with urllib.request.urlopen(request, timeout=40) as response:
        result = json.load(response)
    if not result.get("ok"):
        raise RuntimeError(f"Telegram {method} failed")
    return result["result"]


def git(*args):
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def publish(message):
    message_id = message["message_id"]
    chat_id = message["chat"]["id"]
    text = message["text"]
    timestamp = datetime.fromtimestamp(
        message["date"], timezone.utc
    )

    # Telegram message IDs are unique within a chat.
    filename = f"{timestamp:%Y-%m-%d-%H%M%S}-{chat_id}-{message_id}.md"
    destination = TRANSMISSIONS / filename

    if destination.exists():
        return "already-published"

    # Don't mix automatic commits with unrelated local edits.
    if git("status", "--porcelain").stdout.strip():
        raise RuntimeError("Git working tree is not clean")

    git("pull", "--ff-only", "origin", "main")

    TRANSMISSIONS.mkdir(parents=True, exist_ok=True)

    front_matter = {
        "date": timestamp.isoformat(),
        "title": f"Transmission {message_id}",
        "draft": False,
    }

    lines = ["+++"]
    for key, value in front_matter.items():
        lines.append(f"{key} = {json.dumps(value)}")
    lines.extend(["+++", "", text, ""])

    destination.write_text("\n".join(lines), encoding="utf-8")

    subprocess.run(
        ["hugo", "--gc", "--minify"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    relative_path = destination.relative_to(ROOT)
    git("add", str(relative_path))
    git("commit", "-m", f"Publish transmission {message_id}")
    git("push", "origin", "main")

    return "published"


def main():
    token = os.environ.get("SPYKESPACE_BOT_TOKEN")
    if not token:
        token = getpass.getpass("Telegram bot token: ").strip()

    print("SpykeSpace receiver running. Press Ctrl+C to stop.")

    # Start with new updates only. Old pending updates are skipped.
    pending = telegram(token, "getUpdates", {"offset": -1, "timeout": 0})
    if pending:
        offset = pending[-1]["update_id"] + 1
    else:
        offset = None

    while True:
        try:
            params = {"timeout": POLL_SECONDS}
            if offset is not None:
                params["offset"] = offset

            updates = telegram(token, "getUpdates", params)

            for update in updates:
                next_offset = update["update_id"] + 1
                message = update.get("message", {})

                if message.get("from", {}).get("id") != AUTHORIZED_USER:
                    offset = next_offset
                    continue

                if "text" not in message:
                    telegram(token, "sendMessage", {
                        "chat_id": message["chat"]["id"],
                        "text": "Text transmissions only for now.",
                    })
                    offset = next_offset
                    continue

                try:
                    status = publish(message)
                    reply = (
                        "📡 Transmission submitted to SpykeSpace."
                        if status == "published"
                        else "This transmission already exists."
                    )
                    telegram(token, "sendMessage", {
                        "chat_id": message["chat"]["id"],
                        "text": reply,
                    })
                    offset = next_offset
                except Exception as error:
                    print("Publishing failed:", error)
                    # Retry this update on the next polling cycle.
                    break

        except (urllib.error.URLError, RuntimeError) as error:
            print("Receiver error:", error)
            time.sleep(5)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nReceiver stopped.")

