"""Temporary image/audio/video sessions (standard library only).

Upload: python media_session.py http://DEVICE_IP:8081 --credentials credentials.json --file clip.mp4
State:  python media_session.py http://DEVICE_IP:8081 --credentials credentials.json --state
Pause:  python media_session.py http://DEVICE_IP:8081 --credentials credentials.json --session UUID --action pause
Close:  python media_session.py http://DEVICE_IP:8081 --credentials credentials.json --close UUID
Files stream from disk; media resources are not persisted on the device.
"""
import argparse
import hashlib
import hmac
import http.client
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit
import uuid

from local_api import APIError, LocalAPI

ROOT = "/v1/api/data/user/media"


def upload(api, file, options):
    file = Path(file)
    size = file.stat().st_size
    if not 0 < size <= 128 << 20:
        raise ValueError("The file must contain 1 byte to 128 MiB.")
    path = ROOT + "/sessions"
    boundary = "codie-media-" + uuid.uuid4().hex
    head = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="request"\r\n'
        'Content-Type: application/json\r\n\r\n'
        + json.dumps(options, separators=(",", ":"))
        + f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="media"\r\n'
        'Content-Type: application/octet-stream\r\n\r\n'
    ).encode()
    tail = f"\r\n--{boundary}--\r\n".encode()
    headers = api.headers("POST", path)
    headers["X-Local-Payload-Mode"] = "multipart"
    headers["X-Local-Body-Hash"] = "UNSIGNED-PAYLOAD"
    canonical = "|".join(("POST", unquote(path), headers["X-Local-Timestamp"], headers["X-Local-Nonce"],
                          "multipart", "UNSIGNED-PAYLOAD", api.credentials["user_id"]))
    headers["X-Local-Sig"] = hmac.new(api.credentials["local_secret"].encode(), canonical.encode(), hashlib.sha256).hexdigest()
    headers["Content-Type"] = "multipart/form-data; boundary=" + boundary
    headers["Content-Length"] = str(len(head) + size + len(tail))
    target = urlsplit(api.base_url)
    connection_type = http.client.HTTPSConnection if target.scheme == "https" else http.client.HTTPConnection
    connection = connection_type(target.hostname, target.port, timeout=120)
    try:
        connection.putrequest("POST", target.path.rstrip("/") + path)
        for key, value in headers.items():
            connection.putheader(key, value)
        connection.endheaders()
        connection.send(head)
        with file.open("rb") as source:
            while chunk := source.read(64 << 10):
                connection.send(chunk)
        connection.send(tail)
        response = connection.getresponse()
        raw = response.read()
        try:
            result = json.loads(raw)
        except ValueError:
            result = raw.decode(errors="replace")
        if response.status >= 400:
            raise APIError(response.status, result)
        return result
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--credentials", required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file")
    group.add_argument("--state", action="store_true")
    group.add_argument("--capabilities", action="store_true")
    group.add_argument("--close")
    group.add_argument("--session")
    parser.add_argument("--action", choices=("pause", "resume", "seek", "set_volume", "set_muted", "set_layout"))
    parser.add_argument("--kind", choices=("image", "audio", "video"), help="Controls request fields; the device identifies actual content.")
    parser.add_argument("--x-percent", type=float, default=10)
    parser.add_argument("--y-percent", type=float, default=10)
    parser.add_argument("--width-percent", type=float, default=80)
    parser.add_argument("--height-percent", type=float, default=50)
    parser.add_argument("--fit", choices=("contain", "cover", "stretch"), default="contain")
    parser.add_argument("--max-duration-ms", type=int)
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--muted", choices=("true", "false"), default="false")
    parser.add_argument("--volume", type=float, default=1)
    parser.add_argument("--position-ms", type=int, default=0)
    parser.add_argument("--conflict-policy", choices=("reject", "replace"), default="reject")
    parser.add_argument("--request-id", default=None)
    args = parser.parse_args()
    credentials_file = Path(args.credentials)
    api = LocalAPI(args.url, json.loads(credentials_file.read_text()) if credentials_file.exists() else None)
    if not api.credentials:
        api.pair(lambda: input("Pairing code shown on device: ").strip())
        with credentials_file.open("x", encoding="utf-8") as target:
            json.dump(api.credentials, target)
        credentials_file.chmod(0o600)
    layout = dict(x_percent=args.x_percent, y_percent=args.y_percent, width_percent=args.width_percent,
                  height_percent=args.height_percent, fit=args.fit)
    request_id = args.request_id or str(uuid.uuid4())
    if args.file:
        suffix = Path(args.file).suffix.lower()
        kind = args.kind or ("audio" if suffix in (".mp3", ".wav") else "video" if suffix == ".mp4" else "image")
        options = dict(request_id=request_id, conflict_policy=args.conflict_policy)
        if kind != "audio":
            options["layout"] = layout
        if kind != "image":
            options["playback"] = dict(loop=args.loop, muted=args.muted == "true", volume=args.volume, start_position_ms=args.position_ms)
        if args.max_duration_ms is not None:
            options["max_duration_ms"] = args.max_duration_ms
        print("request_id: " + request_id, flush=True)
        result = upload(api, args.file, options)
    elif args.session:
        path = ROOT + "/sessions/" + str(uuid.UUID(args.session))
        if args.action:
            options = dict(request_id=request_id, action=args.action)
            field = {"seek": ("position_ms", args.position_ms), "set_volume": ("volume", args.volume),
                     "set_muted": ("muted", args.muted == "true"), "set_layout": ("layout", layout)}.get(args.action)
            if field:
                options[field[0]] = field[1]
            result = api.request("POST", path + "/actions", options)
        else:
            result = api.request("GET", path)
    elif args.close:
        result = api.request("DELETE", ROOT + "/sessions/" + str(uuid.UUID(args.close)))
    else:
        result = api.request("GET", ROOT + ("/capabilities" if args.capabilities else "/sessions"))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
