#!/usr/bin/env python3
"""Register a virtual tool and serve calls over the dedicated WebSocket.

Dependencies: python -m pip install websocket-client
Use an existing credentials file created by local_api.py.
This example keeps the supplied integration ID stable across restarts.
External tools are available to both CODE27 and custom provider models.
"""
import argparse
import json
from pathlib import Path

from local_api import LocalAPI


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("device", help="http://DEVICE_IP:8081")
    parser.add_argument("integration_id", help="A stable lowercase UUID chosen by this application")
    parser.add_argument("--credentials", default="credentials.json")
    args = parser.parse_args()
    import websocket

    api = LocalAPI(args.device, json.loads(Path(args.credentials).read_text()))
    root = "/v1/api/data/user/tool-integrations/" + args.integration_id
    # Read the current revision so an existing installation can be updated safely.
    from local_api import APIError
    revision = 0
    try:
        revision = api.request("GET", root)["data"]["revision"]
    except APIError as error:
        if error.status != 404:
            raise
    schema = {"type": "object", "properties": {"text": {"type": "string", "maxLength": 256}},
              "required": ["text"], "additionalProperties": False}
    catalog = {"protocol_version": "v1", "expected_revision": revision,
               "name": "Virtual echo application", "enabled": True, "tools": [
                   {"name": "echo_text", "version": "v1", "description": "Echo a short text through the connected virtual application.",
                    "parameters": schema, "result_schema": schema, "risk": "read",
                    "idempotent": True, "confirmation_required": False, "timeout_ms": 5000}]}
    result = api.request("PUT", root, catalog)
    print("Registered:", args.integration_id, "revision", result["data"]["revision"])
    path = "/v1/ws/tool-integrations/" + args.integration_id + "/executor"
    conn = websocket.create_connection(api.websocket_url(path), timeout=30)
    try:
        ready = json.loads(conn.recv())
        if ready.get("type") != "ready":
            raise RuntimeError("Expected ready message")
        print("Online. Ask the device to echo a short text through the virtual application.")
        conn.settimeout(None)
        while True:
            raw = conn.recv()
            if not raw:
                break
            message = json.loads(raw)
            if message["type"] == "invoke":
                call = message["data"]
                result = {"invocation_id": call["invocation_id"], "status": "succeeded",
                          "data": {"text": call["arguments"]["text"]}}
                conn.send(json.dumps({"type": "result", "data": result}, ensure_ascii=False))
            elif message["type"] == "error":
                print("Protocol error:", message["data"]["code"])
    except KeyboardInterrupt:
        pass
    finally:
        conn.close()


if __name__ == "__main__":
    main()
