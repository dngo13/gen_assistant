"""Python example: pair, chat by text or microphone, or read supplied text directly.
Usage: python local_api.py http://DEVICE_IP:8081 "Hello" --credentials credentials.json
Voice: python local_api.py http://DEVICE_IP:8081 --mic --seconds 10
Voice dependencies: python -m pip install websocket-client sounddevice av
Text mode only needs the Python standard library. Voice replies play automatically as they arrive.
Do not include /v1/api in the device URL. Enter the pairing code shown on the device on the first run; subsequent runs reuse the saved credentials.
Query this turn by turn_id; a new turn replaces the active conversation.
Use --speech device for a spoken chat reply, or --tts to read the supplied text directly.
"""
import argparse
import hashlib
import hmac
import io
import json
import math
import os
from pathlib import Path
import queue
import struct
import sys
import threading
import time
import uuid
from urllib.error import HTTPError
from urllib.parse import unquote, urlsplit, urlencode
from urllib.request import Request, urlopen


class APIError(Exception):
    def __init__(self, status, payload):
        super().__init__(f"HTTP {status}: {payload}")
        self.status = status
        self.payload = payload


class AudioSegment(io.RawIOBase):
    """A bounded, non-seekable audio input consumed by the decoder thread."""
    def __init__(self):
        super().__init__()
        self.chunks = queue.Queue(maxsize=128)
        self.pending = b""
        self.ended = False
        self.aborted = threading.Event()

    def readable(self):
        return True

    def feed(self, data):
        try:
            self.chunks.put_nowait(data)
        except queue.Full as error:
            raise RuntimeError("Local audio playback queue is full.") from error

    def read(self, size=-1):
        if size == 0:
            return b""
        while not self.pending and not self.ended:
            if self.aborted.is_set():
                raise OSError("Audio playback cancelled.")
            try:
                self.pending = self.chunks.get(timeout=0.1)
            except queue.Empty:
                continue
            if not self.pending:
                self.ended = True
        if self.aborted.is_set():
            raise OSError("Audio playback cancelled.")
        count = len(self.pending) if size < 0 else min(size, len(self.pending))
        data, self.pending = self.pending[:count], self.pending[count:]
        return data


class AudioPlayer:
    """Decode and play segments in order while the WebSocket keeps receiving."""
    def __init__(self, av, sounddevice, device):
        self.av, self.sounddevice, self.device = av, sounddevice, device
        self.segments = queue.Queue(maxsize=8)
        self.sources = []
        self.stopped = threading.Event()
        self.error = None
        self.output = None
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def check(self):
        if self.error is not None:
            raise RuntimeError(f"Local audio playback failed: {self.error}") from self.error

    def enqueue_segment(self, item, deadline=None):
        while not self.stopped.is_set():
            self.check()
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError("Local audio playback timed out.")
            try:
                self.segments.put(item, timeout=0.1)
                return
            except queue.Full:
                continue
        raise RuntimeError("Local audio playback cancelled.")

    def start_segment(self, audio, deadline=None):
        self.check()
        if (audio["format"], audio["container"]) not in {("opus", "ogg"), ("mp3", "mp3"), ("wav", "wav")}:
            raise RuntimeError(f"Unsupported client audio format: {audio}")
        if audio["sample_rate"] <= 0 or audio["channels"] <= 0:
            raise RuntimeError("Invalid audio sample rate or channels.")
        source = AudioSegment()
        self.enqueue_segment((audio, source), deadline)
        self.sources.append(source)
        return source

    def run(self):
        try:
            while not self.stopped.is_set():
                try:
                    item = self.segments.get(timeout=0.1)
                except queue.Empty:
                    continue
                if item is None:
                    return
                audio, source = item
                rate, channels = audio["sample_rate"], audio["channels"]
                with self.av.open(source, mode="r", format=audio["container"], buffer_size=4096,
                                  options={"probesize": "4096", "analyzeduration": "0"}) as container:
                    with self.sounddevice.RawOutputStream(samplerate=rate, channels=channels,
                                                         dtype="int16", device=self.device) as output:
                        self.output = output
                        resampler = self.av.AudioResampler(format="s16", rate=rate)
                        def play(frame):
                            if self.stopped.is_set():
                                raise OSError("Audio playback cancelled.")
                            if len(frame.layout.channels) != channels:
                                raise RuntimeError("Decoded audio channel count differs from metadata.")
                            # Packed PCM planes can include alignment padding after the samples.
                            output.write(bytes(frame.planes[0])[:frame.samples * channels * 2])
                        for frame in container.decode(audio=0):
                            for converted in resampler.resample(frame):
                                play(converted)
                        for converted in resampler.resample(None):
                            play(converted)
                        self.output = None
        except Exception as error:
            if not self.stopped.is_set():
                self.error = error

    def finish(self, timeout):
        deadline = time.monotonic() + timeout
        self.enqueue_segment(None, deadline)
        self.thread.join(max(0, deadline - time.monotonic()))
        self.check()
        if self.thread.is_alive():
            raise TimeoutError("Local audio playback timed out.")

    def close(self):
        self.stopped.set()
        for source in self.sources:
            source.aborted.set()
        if self.output is not None:
            try:
                self.output.abort()
            except Exception:
                pass
        self.thread.join(5)


class LocalAPI:
    def __init__(self, base_url, credentials=None):
        self.base_url = base_url.rstrip("/")
        url = urlsplit(self.base_url)
        if url.scheme not in ("http", "https") or not url.netloc or url.path or url.query or url.fragment:
            raise ValueError("Use a device URL such as http://10.0.0.101:8081, without an API path or query parameters.")
        self.credentials = credentials or {}

    def headers(self, method, path, body=b"", mode="empty"):
        timestamp = str(int(time.time()))
        nonce = str(uuid.uuid4())
        user_id = self.credentials.get("user_id", "")
        # Use the UTF-8 bytes of the original local_secret string; do not decode it as hexadecimal.
        body_hash = hashlib.sha256(body).hexdigest()
        canonical = "|".join((method.upper(), unquote(urlsplit(path).path), timestamp, nonce, mode, body_hash, user_id))
        signature = hmac.new(self.credentials["local_secret"].encode(), canonical.encode(), hashlib.sha256).hexdigest()
        result = {"X-Local-Sig": signature, "X-Local-Timestamp": timestamp,
                  "X-Local-Nonce": nonce, "X-Local-Payload-Mode": mode,
                  "X-Local-Body-Hash": body_hash, "X-Local-User-Id": user_id}
        if self.credentials.get("local_session_id"):
            result["X-Local-Session-Id"] = self.credentials["local_session_id"]
        return result

    def websocket_url(self, path):
        headers = self.headers("GET", path)
        fields = {"sig": "X-Local-Sig", "timestamp": "X-Local-Timestamp", "nonce": "X-Local-Nonce",
                  "payload_mode": "X-Local-Payload-Mode", "body_hash": "X-Local-Body-Hash",
                  "user_id": "X-Local-User-Id", "session_id": "X-Local-Session-Id"}
        query = urlencode({key: headers[value] for key, value in fields.items() if value in headers})
        base = self.base_url.replace("https://", "wss://", 1).replace("http://", "ws://", 1)
        return base + path + "?" + query

    def request(self, method, path, payload=None, *, public=False, timeout=30):
        body = b"" if payload is None else json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        mode = "json" if payload is not None else "empty"
        headers = {} if public else self.headers(method, path, body, mode)
        if payload is not None:
            headers["Content-Type"] = "application/json"
        request = Request(self.base_url + path, data=body if method.upper() != "GET" else None,
                          headers=headers, method=method.upper())
        try:
            with urlopen(request, timeout=timeout) as response:
                raw = response.read()
                return json.loads(raw)
        except HTTPError as error:
            raw = error.read()
            try:
                payload = json.loads(raw)
            except (ValueError, UnicodeDecodeError):
                payload = raw.decode(errors="replace")
            # Preserve structured error details; do not automatically retry writes.
            raise APIError(error.code, payload) from error

    def pair(self, read_code, auth_scope="session"):
        bootstrap = self.request("GET", "/v1/api/auth/bootstrap", public=True)["data"]
        challenge = self.request("POST", "/v1/api/auth/pair/request", public=True)["data"]
        result = self.request("POST", "/v1/api/auth/pair/confirm", {
            "challenge_id": challenge["challenge_id"], "pairing_code": read_code(), "auth_scope": auth_scope
        }, public=True)["data"]
        # REST clients only need these credentials; ignore additional Agent Service fields.
        self.credentials = {key: result[key] for key in ("local_secret", "local_session_id", "local_session_expires_at_ms", "auth_scope") if key in result}
        self.credentials["user_id"] = bootstrap.get("user_id", "")
        return self.credentials

    def speak(self, text, timeout=180):
        slot = self.request("GET", "/v1/api/data/user/slot")["data"]["slot_number"]
        path = "/v1/api/data/user/tts/utterances"
        task = self.request("POST", path, {
            "request_id": str(uuid.uuid4()), "slot": slot, "text": text
        })["data"]
        utterance_id = task["utterance_id"]
        print("Speech submitted. Utterance ID: " + utterance_id, flush=True)
        return self.wait_for_completion(path + "/" + utterance_id, timeout)

    def chat(self, text, timeout=120, speech="none"):
        if speech not in ("none", "device"):
            raise ValueError("Speech output must be none or device.")
        slot = self.request("GET", "/v1/api/data/user/slot")["data"]["slot_number"]
        device = self.request("GET", "/v1/api/data/user/device/state")["data"]
        if device["conversation_blocked"]:
            raise RuntimeError("The device currently blocks chat requests.")
        result = self.request("POST", "/v1/api/data/user/chat/turns", {
            "request_id": str(uuid.uuid4()), "slot": slot,
            "input": {"type": "text", "text": text}, "output": {"speech": speech}
        })["data"]
        turn_id = result["turn_id"]
        print("Chat submitted. Turn ID: " + turn_id, flush=True)
        task = self.wait_for_completion("/v1/api/data/user/chat/turns/" + turn_id, timeout)
        return [task["assistant_text"]]

    def wait_for_completion(self, path, timeout):
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Task timed out: " + path)
            task = self.request("GET", path, timeout=min(30, remaining))["data"]
            if task["state"] == "completed":
                return task
            if task["state"] in ("failed", "cancelled"):
                error = task.get("error") or {}
                code = error.get("code") or task["state"]
                reason = " (" + error["reason"] + ")" if error.get("reason") else ""
                raise RuntimeError("Task stopped [" + code + "]" + reason + ": " + (error.get("message") or task["state"]))
            time.sleep(min(1, max(0, deadline - time.monotonic())))

    def chat_microphone(self, seconds=10, input_device=None, output_device=None, timeout=180):
        try:
            import av
            import sounddevice
            import websocket
        except ImportError as error:
            raise RuntimeError("Voice dependencies: python -m pip install websocket-client sounddevice av") from error
        try:
            sounddevice.check_input_settings(device=input_device, samplerate=16000, channels=1, dtype="int16")
            sounddevice.query_devices(output_device, "output")
        except sounddevice.PortAudioError as error:
            raise RuntimeError(f"Audio device unavailable: {error}") from error
        slot = self.request("GET", "/v1/api/data/user/slot")["data"]["slot_number"]
        turn = self.request("POST", "/v1/api/data/user/chat/turns", {
            "request_id": str(uuid.uuid4()), "slot": slot,
            "input": {"type": "audio_stream", "audio": {
                "format": "pcm_s16le", "sample_rate": 16000, "channels": 1, "container": "raw"}},
            "output": {"speech": "client"},
        })["data"]
        turn_path = "/v1/api/data/user/chat/turns/" + turn["turn_id"]
        stream_path = "/v1/ws/chat/turns/" + turn["turn_id"] + "/audio"
        print("Chat submitted. Turn ID: " + turn["turn_id"], flush=True)
        conn, player, current = None, None, None
        terminal, audio_ended = False, False
        sequence, segment = 0, 0
        deadline = time.monotonic() + timeout
        try:
            conn = websocket.create_connection(self.websocket_url(stream_path), timeout=timeout)
            first = json.loads(conn.recv())
            if first.get("type") != "ready":
                raise RuntimeError(first)
            player = AudioPlayer(av, sounddevice, output_device)
            with sounddevice.RawInputStream(samplerate=16000, channels=1, dtype="int16",
                                           blocksize=320, device=input_device) as microphone:
                print(f"Recording: speak into your microphone ({seconds} seconds).", flush=True)
                for index in range(1, seconds * 50 + 1):
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Voice input timed out.")
                    data, overflowed = microphone.read(320)
                    if overflowed:
                        raise RuntimeError("Microphone overflow: captured audio was lost.")
                    data = bytes(data)
                    if sys.byteorder != "little":
                        data = b"".join(data[offset:offset + 2][::-1] for offset in range(0, len(data), 2))
                    conn.send_binary(struct.pack(">I", index) + data)
            conn.send(json.dumps({"type": "input.complete"}))
            print("Recording finished. Reply audio will play automatically.", flush=True)
            conn.settimeout(1)
            while time.monotonic() < deadline:
                player.check()
                try:
                    message = conn.recv()
                except websocket.WebSocketTimeoutException:
                    continue
                if isinstance(message, bytes):
                    if current is None or len(message) <= 4:
                        raise RuntimeError("Audio arrived outside a segment.")
                    received = struct.unpack(">I", message[:4])[0]
                    if received != sequence + 1:
                        raise RuntimeError("Audio sequence is not consecutive.")
                    current.feed(message[4:])
                    sequence = received
                    continue
                if not message:
                    raise RuntimeError("Audio connection closed before turn.end.")
                event = json.loads(message)
                kind = event["type"]
                if kind == "audio.start":
                    if current is not None or audio_ended or event["segment"] != segment + 1:
                        raise RuntimeError("Unexpected audio segment start.")
                    segment = event["segment"]
                    current = player.start_segment(event["audio"], deadline)
                elif kind == "audio.segment.end":
                    if current is None or event["segment"] != segment or event["sequence"] != sequence:
                        raise RuntimeError("Audio segment end does not match received audio.")
                    current.feed(b"")
                    current = None
                elif kind == "audio.end":
                    if current is not None or audio_ended or not sequence or event["sequence"] != sequence:
                        raise RuntimeError("Audio has not been fully received.")
                    audio_ended = True
                    # The API acknowledgement confirms delivery; local playback may still be draining.
                    conn.send(json.dumps({"type": "audio.ack", "sequence": sequence}))
                elif kind == "turn.end":
                    terminal = True
                    turn = event["turn"]
                    if turn["state"] != "completed":
                        raise RuntimeError(turn.get("error") or turn["state"])
                    if not audio_ended:
                        raise RuntimeError("Turn completed without audio.end.")
                    player.finish(max(0, deadline - time.monotonic()))
                    return turn["assistant_text"]
                else:
                    raise RuntimeError("Unknown audio event: " + kind)
            raise TimeoutError("Voice reply timed out. Turn ID: " + turn["turn_id"])
        except (sounddevice.PortAudioError, websocket.WebSocketException) as error:
            raise RuntimeError(f"Voice chat failed: {error}") from error
        finally:
            # Cancel while the stream is connected so the device receives an intentional stop.
            if not terminal:
                try:
                    self.request("POST", turn_path + "/cancel")
                except Exception:
                    pass
            if player is not None:
                player.close()
            if conn is not None:
                conn.close()



def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("device", nargs="?")
    parser.add_argument("text", nargs="?")
    parser.add_argument("--credentials", default="credentials.json")
    parser.add_argument("--auth-scope", default="session")
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--speech", choices=("none", "device"), default="none")
    parser.add_argument("--mic", action="store_true")
    parser.add_argument("--seconds", type=int, default=10)
    parser.add_argument("--input-device", type=int)
    parser.add_argument("--output-device", type=int)
    parser.add_argument("--list-audio-devices", action="store_true")
    parser.add_argument("--tts", action="store_true")
    parser.add_argument("--help", "-h", action="store_true")
    args = parser.parse_args()
    if args.help:
        print(__doc__)
        print("Options: --credentials credentials file; --auth-scope session or permanent; --timeout reply timeout in seconds (default: 120); --speech none or device (default: none); --tts reads supplied text directly.")
        print("Voice: --mic records and plays locally; --seconds 1..30 (default: 10); --input-device / --output-device select device IDs; --list-audio-devices lists devices.")
        return
    if args.list_audio_devices:
        try:
            import sounddevice
        except ImportError as error:
            raise RuntimeError("Install microphone support: python -m pip install sounddevice") from error
        print(sounddevice.query_devices())
        return
    if not args.device or (not args.mic and (not args.text or not args.text.strip())):
        raise ValueError("Provide a device URL and either chat text or --mic. Use --help for usage.")
    if args.mic and (args.text is not None or args.speech != "none"):
        raise ValueError("--mic uses local microphone and speakers; do not combine it with text or --speech device.")
    if not 1 <= args.seconds <= 30:
        raise ValueError("Recording duration must be 1..30 seconds.")
    if args.auth_scope not in ("session", "permanent") or not math.isfinite(args.timeout) or args.timeout <= 0:
        raise ValueError("Auth scope must be session or permanent; timeout must be a finite positive number.")
    if args.tts and (args.mic or args.speech != "none"):
        raise ValueError("Use --tts with text; do not combine it with --mic or --speech device.")
    api = LocalAPI(args.device)
    credentials_file = Path(args.credentials)
    try:
        api.credentials = json.loads(credentials_file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        api.pair(lambda: input("Enter the pairing code shown on the device: ").strip(), args.auth_scope)
        # Create the credentials file exclusively with owner-only read/write permissions; never overwrite an existing file.
        descriptor = os.open(credentials_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(api.credentials, output, ensure_ascii=False, indent=2)
            output.write("\n")
        print("Pairing succeeded. Credentials saved.")
    if args.mic:
        print("Assistant reply: " + api.chat_microphone(args.seconds, args.input_device, args.output_device, args.timeout))
    elif args.tts:
        api.speak(args.text.strip(), args.timeout)
        print("Speech playback completed.")
    else:
        for reply in api.chat(args.text.strip(), args.timeout, args.speech):
            print("Assistant reply: " + reply)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Cancelled.", file=sys.stderr)
        sys.exit(130)
    except (OSError, ValueError, RuntimeError, APIError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
