#!/usr/bin/env python3
"""Calendar and Home Assistant weather tools for the CODE27.

It registers get_calendar_events and get_current_weather on the device, then stays
connected. Calendar requests use the Flask backend; weather requests read the
weather.forecast_home entity from Home Assistant.

Setup (once):
  python -m pip install websocket-client requests
  Keep local_api.py (from the API package's examples/ folder) in the same folder as this file.

Check the backend first (no device needed):
  python calendar_tool.py --backend http://localhost:5000 --dry-run today

Run it:
  python calendar_tool.py http://10.0.0.101:8081 --backend http://localhost:5000
  Set HA_BASE_URL and HA_TOKEN for current weather lookups.

First run asks for the pairing code shown on the device and saves credentials_permanent.json
(permanent credentials, so the script survives device restarts). After the tool is registered,
start a NEW conversation on the device: tools are frozen into each session when it starts.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

from local_api import APIError, LocalAPI

# Stable ID for this integration. Keep it the same across restarts so updates replace the old catalog.
INTEGRATION_ID = "5b1f0c7e-3a42-4d8e-9c61-7e2a0d4f8b13"
TOOL_NAME = "get_calendar_events"
DAYS = ("today", "tomorrow", "next_7_days")
LABELS = {"today": "today", "tomorrow": "tomorrow", "next_7_days": "in the next 7 days"}

EVENT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "maxLength": 80},
        "date": {"type": "string", "maxLength": 10, "description": "YYYY-MM-DD"},
        "start": {"type": "string", "maxLength": 12, "description": "Local start time, or 'All day'"},
        "end": {"type": "string", "maxLength": 12},
        "all_day": {"type": "boolean"},
        "description": {"type": "string", "maxLength": 120},
    },
    "required": ["title", "date", "start", "end", "all_day", "description"],
    "additionalProperties": False,
}
PARAMETERS = {
    "type": "object",
    "properties": {
        "day": {"type": "string", "enum": list(DAYS), "description": "Which day to look up."},
    },
    "required": ["day"],
    "additionalProperties": False,
}
RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "date": {"type": "string", "maxLength": 10, "description": "First day covered, YYYY-MM-DD"},
        "events": {"type": "array", "maxItems": 15, "items": EVENT_SCHEMA},
        "message": {"type": "string", "maxLength": 200},
    },
    "required": ["date", "events", "message"],
    "additionalProperties": False,
}
WEATHER_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "temperature": {"type": "string", "maxLength": 32},
        "unit": {"type": "string", "maxLength": 16},
        "condition": {"type": "string", "maxLength": 80},
        "message": {"type": "string", "maxLength": 300},
    },
    "required": ["temperature", "unit", "condition", "message"],
    "additionalProperties": False,
}
WEATHER_EMPTY_RESULT = {
    "temperature": "",
    "unit": "",
    "condition": "",
    "message": "",
}


def build_catalog(revision):
    return {
        "protocol_version": "v1",
        "expected_revision": revision,
        "name": "Google Calendar",
        "enabled": True,
        "tools": [{
            "name": TOOL_NAME,
            "version": "v1",
            "description": ("Look up the user's calendar events for today, tomorrow or the next 7 days. "
                            "Use it whenever the user asks what is on their schedule, calendar, agenda or what "
                            "they have to do. Events come back sorted by start time. Read only."),
            "parameters": PARAMETERS,
            "result_schema": RESULT_SCHEMA,
            "risk": "read",
            "idempotent": True,
            "confirmation_required": False,
            "timeout_ms": 15000,
        }, {
            "name": "get_current_weather",
            "version": "v1",
            "description": (
                "Read the current condition and temperature from Home Assistant's "
                "weather.forecast_home entity. Use when the user asks about current weather."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            "result_schema": WEATHER_RESULT_SCHEMA,
            "risk": "read",
            "idempotent": True,
            "confirmation_required": False,
            "timeout_ms": 10000,
        }],
    }


def fetch_calendar(backend, day, timeout):
    """Ask the Flask backend for events and shape them to RESULT_SCHEMA."""
    response = requests.get(backend.rstrip("/") + "/events", params={"day": day}, timeout=timeout)
    response.raise_for_status()
    body = response.json()
    events = body["events"]
    if events:
        message = f"{len(events)} event(s) {LABELS[day]}."
        if body.get("truncated"):
            message += " More events exist than were returned."
    else:
        message = f"No events {LABELS[day]}."
    return {"date": body["date"], "events": events, "message": message}

def fetch_weather(home_assistant_url, token, timeout):
    """Read the current weather entity through Home Assistant's REST API."""
    if not home_assistant_url or not token:
        raise RuntimeError("HA_BASE_URL and HA_TOKEN are required for weather lookup.")
    response = requests.get(
        home_assistant_url.rstrip("/") + "/api/states/weather.forecast_home",
        headers={"Authorization": f"Bearer {token}"},
        timeout=timeout,
    )
    response.raise_for_status()
    entity = response.json()
    attributes = entity.get("attributes") or {}
    temperature_value = attributes.get("temperature")
    temperature = "unknown" if temperature_value is None else str(temperature_value)
    unit = str(attributes.get("temperature_unit") or "°F")
    condition = str(entity.get("state") or "unknown")
    return {
        "temperature": temperature,
        "unit": unit,
        "condition": condition,
        "message": f"Current weather: {condition}, {temperature}{unit}.",
    }


def failed(invocation_id, code, message, data=None):
    return {"invocation_id": invocation_id, "status": "failed", "code": code,
            "data": data or {"date": "", "events": [], "message": message}}


def handle_invoke(call, backend, home_assistant_url="", home_assistant_token=""):
    """Turn one device tool call into a result message body."""
    invocation_id = call["invocation_id"]
    tool_name = call.get("name")
    if tool_name == "get_current_weather":
        try:
            data = fetch_weather(
                home_assistant_url,
                home_assistant_token,
                max(1.0, min(8.0, call.get("deadline_unix_ms", 0) / 1000 - time.time() - 1)),
            )
        except (requests.RequestException, RuntimeError, ValueError, TypeError, KeyError) as error:
            print("Home Assistant weather lookup failed:", error, flush=True)
            return failed(
                invocation_id,
                "WEATHER_UNAVAILABLE",
                "The current weather could not be reached.",
                WEATHER_EMPTY_RESULT,
            )
        return {"invocation_id": invocation_id, "status": "succeeded", "data": data}
    if tool_name != TOOL_NAME:
        return failed(invocation_id, "UNKNOWN_TOOL", "Unknown tool.")
    day = (call.get("arguments") or {}).get("day")
    if day not in DAYS:
        return failed(invocation_id, "BAD_ARGUMENT", "day must be today, tomorrow or next_7_days.")
    remaining = call.get("deadline_unix_ms", 0) / 1000 - time.time()
    timeout = max(1.0, min(10.0, remaining - 1))
    try:
        data = fetch_calendar(backend, day, timeout)
    except Exception as error:
        print("Calendar lookup failed:", error, flush=True)
        return failed(invocation_id, "CALENDAR_UNAVAILABLE", "The calendar could not be reached right now.")
    return {"invocation_id": invocation_id, "status": "succeeded", "data": data}


def register(api):
    root = "/v1/api/data/user/tool-integrations/" + INTEGRATION_ID
    for attempt in range(2):
        try:
            revision = api.request("GET", root)["data"]["revision"]
        except APIError as error:
            if error.status != 404:
                raise
            revision = 0
        try:
            result = api.request("PUT", root, build_catalog(revision))
            print("Registered tool", TOOL_NAME, "- revision", result["data"]["revision"], flush=True)
            return
        except APIError as error:
            if error.status != 409 or attempt:  # 409 = revision changed, re-read once and retry
                raise


def serve(api, backend, home_assistant_url, home_assistant_token):
    import websocket

    path = "/v1/ws/tool-integrations/" + INTEGRATION_ID + "/executor"
    delay = 2
    while True:
        conn = None
        try:
            # The signed URL expires after a few minutes, so build a fresh one for every connection.
            conn = websocket.create_connection(api.websocket_url(path), timeout=30)
            ready = json.loads(conn.recv())
            if ready.get("type") != "ready":
                raise RuntimeError("Expected ready message, got: " + str(ready))
            print("Online. Start a new conversation on the device and ask about your calendar.", flush=True)
            delay = 2
            conn.settimeout(None)
            while True:
                raw = conn.recv()
                if not raw:
                    raise ConnectionError("Connection closed by device")
                message = json.loads(raw)
                if message["type"] == "invoke":
                    call = message["data"]
                    print("Tool call:", call.get("name"), call.get("arguments"), flush=True)
                    result = handle_invoke(call, backend, home_assistant_url, home_assistant_token)
                    conn.send(json.dumps({"type": "result", "data": result}, ensure_ascii=False))
                elif message["type"] == "error":
                    print("Protocol error:", message["data"].get("code"), flush=True)
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


def load_api(device, credentials_path):
    api = LocalAPI(device)
    path = Path(credentials_path)
    if path.exists():
        api.credentials = json.loads(path.read_text(encoding="utf-8"))
    else:
        api.pair(lambda: input("Pairing code shown on the device: ").strip(), "permanent")
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as target:
            json.dump(api.credentials, target, indent=2)
        print("Paired. Credentials saved to", path, flush=True)
    return api


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("device", nargs="?", help="http://10.0.0.101:8081")
    parser.add_argument("--backend", default="http://127.0.0.1:5000", help="Flask backend URL (default: %(default)s)")
    parser.add_argument(
        "--credentials",
        default=os.getenv("CODE27_CREDENTIALS_PATH", "CODE27/integrations/credentials_permanent.json"),
    )
    parser.add_argument("--dry-run", choices=DAYS, help="Only query the backend and print what the device would get")
    args = parser.parse_args()

    if args.dry_run:
        print(json.dumps(fetch_calendar(args.backend, args.dry_run, 15), indent=2, ensure_ascii=False))
        return
    if not args.device:
        parser.error("device URL is required unless --dry-run is used")
    api = load_api(args.device, args.credentials)
    register(api)
    try:
        serve(
            api,
            args.backend,
            os.getenv("HA_BASE_URL", "").strip(),
            os.getenv("HA_TOKEN", "").strip(),
        )
    except KeyboardInterrupt:
        print("Stopped.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, APIError, requests.RequestException) as error:
        print(error, file=sys.stderr)
        sys.exit(1)
