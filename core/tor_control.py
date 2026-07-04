

import logging
import os
import socket
import time
from pathlib import Path

import _path
from platform_utils import app_support_dir

log = logging.getLogger(__name__)

CONTROL_HOST = "127.0.0.1"
CONTROL_PORT = 9051
CONNECT_TIMEOUT_S = 5
COOKIE_PATHS = [
    app_support_dir() / "tor_data" / "control_auth_cookie",
    Path("/var/run/tor/control.authcookie"),
]

NEWNYM_COOLDOWN_S = 15
_last_newnym: float = 0.0

class TorControlError(Exception):
    pass

class TorControl:
    def __init__(self) -> None:
        self._sock: socket.socket | None = None
        self._buf = ""

    def connect(self) -> None:
        self._sock = socket.create_connection(
            (CONTROL_HOST, CONTROL_PORT), timeout=CONNECT_TIMEOUT_S
        )
        self._sock.settimeout(None)
        log.debug("Connected to Tor control port.")

    def close(self) -> None:
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def _send(self, cmd: str) -> None:
        assert self._sock
        self._sock.sendall((cmd.rstrip("\r\n") + "\r\n").encode())

    def _readline(self) -> str:
        assert self._sock
        while "\n" not in self._buf:
            chunk = self._sock.recv(4096).decode(errors="replace")
            if not chunk:
                raise TorControlError("Control port connection closed.")
            self._buf += chunk
        line, self._buf = self._buf.split("\n", 1)
        return line.rstrip("\r")

    def _read_reply(self) -> list[str]:
        lines: list[str] = []
        while True:
            line = self._readline()
            lines.append(line)

            if len(line) >= 4 and line[3] == " ":
                break
            if line.startswith("6"):
                break
        return lines

    def _cmd(self, cmd: str) -> list[str]:
        self._send(cmd)
        reply = self._read_reply()
        code = reply[-1][:3] if reply else "000"
        if not code.startswith("2"):
            raise TorControlError(f"Control command {cmd!r} failed: {reply}")
        return reply

    def authenticate(self) -> None:
        cookie = self._read_cookie()
        hex_cookie = cookie.hex()
        self._cmd(f"AUTHENTICATE {hex_cookie}")
        log.debug("Authenticated with Tor control port.")

    @staticmethod
    def _read_cookie() -> bytes:
        for path in COOKIE_PATHS:
            if path.exists():
                return path.read_bytes()
        raise TorControlError(
            "Tor auth cookie not found. "
            "Ensure CookieAuthentication 1 is set in torrc."
        )

    def new_identity(self) -> bool:
        global _last_newnym
        now = time.monotonic()
        if now - _last_newnym < NEWNYM_COOLDOWN_S:
            wait = NEWNYM_COOLDOWN_S - (now - _last_newnym)
            log.info("NEWNYM cooldown — waiting %.1f s.", wait)
            time.sleep(wait)
        self._cmd("SIGNAL NEWNYM")
        _last_newnym = time.monotonic()
        log.info("NEWNYM sent — new Tor circuits will be built.")
        return True

    def circuit_status(self) -> list[str]:
        reply = self._cmd("GETINFO circuit-status")
        circuits: list[str] = []
        for line in reply:
            if line.startswith("250+") or line.startswith("250-") or line.startswith("250 "):
                content = line[4:].strip()
                if content and content != "OK":
                    circuits.append(content)
        return circuits

    def stream_status(self) -> list[str]:
        reply = self._cmd("GETINFO stream-status")
        streams: list[str] = []
        for line in reply:
            content = line[4:].strip()
            if content and content != "OK":
                streams.append(content)
        return streams

    def subscribe_events(self, events: list[str]) -> None:
        self._cmd(f"SETEVENTS {' '.join(events)}")
        log.info("Subscribed to Tor events: %s", events)

    def monitor(self) -> None:
        self.subscribe_events(["CIRC", "STREAM", "STATUS_CLIENT"])
        log.info("Tor control monitor running.")
        while True:
            try:
                line = self._readline()
            except TorControlError:
                log.warning("Control port disconnected — reconnecting in 5 s.")
                time.sleep(5)
                self.connect()
                self.authenticate()
                self.subscribe_events(["CIRC", "STREAM", "STATUS_CLIENT"])
                continue

            if "650 STATUS_CLIENT" in line and "BOOTSTRAP" in line:
                log.info("Tor status: %s", line.split("650 ", 1)[-1])
            elif "650 CIRC" in line:
                log.debug("Circuit: %s", line)
            elif "650 STREAM" in line:
                log.debug("Stream: %s", line)

def connect() -> TorControl:
    ctrl = TorControl()
    ctrl.connect()
    ctrl.authenticate()
    return ctrl

def run_monitor() -> None:
    import threading
    def _loop() -> None:
        while True:
            try:
                ctrl = connect()
                ctrl.monitor()
            except Exception as exc:
                log.warning("Tor control monitor error: %s — retrying in 10 s.", exc)
                time.sleep(10)
    t = threading.Thread(target=_loop, name="tor-control-monitor", daemon=True)
    t.start()
    log.info("Tor control monitor thread started.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    ctrl = connect()
    print("Circuit status:")
    for c in ctrl.circuit_status():
        print(" ", c)
    print("\nSend NEWNYM? [y/N] ", end="", flush=True)
    if input().strip().lower() == "y":
        ctrl.new_identity()
    ctrl.close()
