#!/usr/bin/env python3
"""Copy everything the CODE27 says to a Discord channel, automatically.

It listens to the device's chat-history events, so it catches voice chats, reminders and
anything else the device says, whoever started it. No Discord command needed.

Setup:
  python -m pip install websocket-client requests
  Keep this file next to local_api.py and calendar_tool.py (it reuses the same pairing).
  Put your webhook in the environment (or a .env file in this folder):
      DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

Run:
  python discord_mirror.py http://DEVICE_IP:8081
  Options: --ping YOUR_DISCORD_USER_ID   (mention you like the current reminders do)
           --name Sirius                 (name shown on the webhook post)
           --include-user                (also post what you said, prefixed with "You:")

Notes: only turns the device saves to chat history are mirrored (retention "full" or "chat",
which is the default for normal chats). Leave it running; it reconnects on its own and
catches up on anything said while it was disconnected.
"""
import argparse
import json
import os
import sys
import time
from collections import OrderedDict, deque

import requests

from calendar_tool import load_api
from local_api import APIError

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

HISTORY = "/v1/api/data/user/chat/history"
FLUSH_AFTER = 1.5  # seconds of quiet before a reply is posted (lets multi-part replies arrive together)


class Mirror:
    def __init__(self, api, webhook, ping=None, name=None, include_user=False):
        self.api, self.webhook, self.ping, self.name, self.include_user = api, webhook, ping, name, include_user
        self.seen = set()
        self.seen_order = deque(maxlen=2000)
        self.pending = OrderedDict()  # turn key -> [(role, text), ...]
        self.first_sync = True

    # ---- helpers -----------------------------------------------------------------
    def mark(self, chat_id):
        if chat_id in self.seen:
            return False
        if len(self.seen_order) == self.seen_order.maxlen:
            self.seen.discard(self.seen_order[0])
        self.seen.add(chat_id)
        self.seen_order.append(chat_id)
        return True

    def wanted(self, item):
        role = (item.get("role") or "").lower()
        text = (item.get("content") or "").strip()
        if not text or str(item.get("content_type") or "").startswith("image"):
            return None
        if role == "assistant" or (role == "user" and self.include_user):
            return role, text
        return None

    def add_items(self, items, post_new=True):
        for item in sorted(items, key=lambda i: i.get("seq", 0)):
            chat_id = item.get("chat_id") or f"{item.get('turn_id')}:{item.get('seq')}"
            if not self.mark(chat_id) or not post_new:
                continue
            entry = self.wanted(item)
            if entry:
                self.pending.setdefault(item.get("turn_id") or chat_id, []).append(entry)

    # ---- HTTP recovery -----------------------------------------------------------
    def catch_up(self):
        """Read recent history over HTTP. First run only marks it as seen; later runs post what was missed."""
        slot = self.api.request("GET", "/v1/api/data/user/slot")["data"]["slot_number"]
        data = self.api.request("GET", f"{HISTORY}?slot={slot}&limit=5")["data"]
        self.add_items(data.get("items", []), post_new=not self.first_sync)
        self.first_sync = False

    # ---- Discord -----------------------------------------------------------------
    def flush(self):
        while self.pending:
            _, entries = self.pending.popitem(last=False)
            lines = [text if role == "assistant" else "You: " + text for role, text in entries]
            self.post("\n".join(lines))

    def post(self, text):
        for start in range(0, len(text), 1900):
            content = text[start:start + 1900]
            body = {"content": content, "allowed_mentions": {"parse": []}}
            if start == 0 and self.ping:
                body["content"] = f"<@{self.ping}> " + content
                body["allowed_mentions"] = {"users": [str(self.ping)]}
            if self.name:
                body["username"] = self.name
            for attempt in range(2):
                try:
                    response = requests.post(self.webhook, json=body, timeout=10)
                except requests.RequestException as error:
                    print("Discord post failed:", error, flush=True)
                    break
                if response.status_code == 429 and attempt == 0:  # rate limited: wait once and retry
                    time.sleep(min(float(response.headers.get("Retry-After", 1)), 10))
                    continue
                if response.status_code >= 300:
                    print("Discord post failed:", response.status_code, flush=True)
                break

    # ---- main loop ---------------------------------------------------------------
    def handle(self, message):
        kind = message.get("type")
        if kind == "chat_history":
            payload = message.get("data", message)
            items = payload.get("items") or []
            if items:
                self.add_items(items)
            else:  # a sync/reset style event with no records: recover over HTTP
                self.catch_up()
        elif kind == "topic_error":
            print("Topic error:", message, flush=True)
        elif kind == "result":
            print("Subscribed:", json.dumps(message.get("data", message))[:200], flush=True)

    def run(self):
        import websocket

        delay = 2
        while True:
            conn = None
            try:
                conn = websocket.create_connection(self.api.websocket_url("/v1/ws/events"), timeout=30)
                ready = json.loads(conn.recv())
                if ready.get("type") != "ready":
                    raise RuntimeError("Expected ready message, got: " + str(ready))
                conn.send(json.dumps({"type": "subscribe", "request_id": "sub-1",
                                      "data": {"events": ["chat_history"]}}))
                self.catch_up()
                self.flush()
                print("Mirroring the CODE27 to Discord.", flush=True)
                delay = 2
                conn.settimeout(FLUSH_AFTER)
                while True:
                    try:
                        raw = conn.recv()
                    except websocket.WebSocketTimeoutException:
                        self.flush()
                        continue
                    if not raw:
                        raise ConnectionError("Connection closed by device")
                    self.handle(json.loads(raw))
            except KeyboardInterrupt:
                raise
            except Exception as error:
                print(f"Disconnected ({error}). Retrying in {delay}s.", flush=True)
                time.sleep(delay)
                delay = min(delay * 2, 30)
            finally:
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("device", help="http://10.0.0.101:8081")
    parser.add_argument("--credentials", default="credentials_permanent.json")
    parser.add_argument("--webhook", default=os.environ.get("DISCORD_WEBHOOK_URL"),
                        help="Discord webhook URL (default: DISCORD_WEBHOOK_URL environment variable)")
    parser.add_argument("--ping", help="Discord user ID to mention")
    parser.add_argument("--name", help="Name shown on the webhook post")
    parser.add_argument("--include-user", action="store_true")
    args = parser.parse_args()
    if not args.webhook:
        parser.error("set DISCORD_WEBHOOK_URL or pass --webhook")
    api = load_api(args.device, args.credentials)
    try:
        Mirror(api, args.webhook, args.ping, args.name, args.include_user).run()
    except KeyboardInterrupt:
        print("Stopped.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, APIError) as error:
        print(error, file=sys.stderr)
        sys.exit(1)
