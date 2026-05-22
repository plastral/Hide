                      

import logging
import random
import socket
import struct
import threading
import time
from urllib.parse import urlparse

from config_loader import CFG

log = logging.getLogger(__name__)

_cfg         = CFG["traffic_padding"]
_tor         = CFG["tor"]

SOCKS_HOST   = _tor["socks_host"]
SOCKS_PORT   = _tor["socks_port"]
MIN_INTERVAL = _cfg["min_interval_s"]
MAX_INTERVAL = _cfg["max_interval_s"]
MIN_BURST    = _cfg["min_burst"]
MAX_BURST    = _cfg["max_burst"]
TIMEOUT_S    = _cfg["request_timeout_s"]
TARGETS      = _cfg["targets"]

_stop_event  = threading.Event()

def _socks5_connect(proxy_host: str, proxy_port: int,
                    dest_host: str, dest_port: int,
                    timeout: float) -> socket.socket:
    s = socket.create_connection((proxy_host, proxy_port), timeout=timeout)
    s.settimeout(timeout)

    s.sendall(b"\x05\x01\x00")
    resp = s.recv(2)
    if len(resp) < 2 or resp[0] != 5 or resp[1] != 0:
        s.close()
        raise OSError(f"SOCKS5 auth negotiation failed: {resp!r}")

    host_b = dest_host.encode()
    request = (
        b"\x05\x01\x00\x03"
        + bytes([len(host_b)])
        + host_b
        + struct.pack(">H", dest_port)
    )
    s.sendall(request)

    reply = s.recv(10)
    if len(reply) < 2 or reply[1] != 0:
        s.close()
        raise OSError(f"SOCKS5 connect refused: reply[1]={reply[1] if len(reply)>1 else '?'}")

    return s

def _http_head(url: str) -> None:
    parsed   = urlparse(url)
    host     = parsed.hostname or url
    port     = parsed.port or (443 if parsed.scheme == "https" else 80)
    use_tls  = parsed.scheme == "https"

    try:
        raw = _socks5_connect(SOCKS_HOST, SOCKS_PORT, host, port, TIMEOUT_S)

        if use_tls:
            import ssl
            ctx = ssl.create_default_context()
            sock = ctx.wrap_socket(raw, server_hostname=host)
        else:
            sock = raw

        request = (
            f"HEAD / HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            f"User-Agent: Mozilla/5.0\r\n"
            f"Connection: close\r\n\r\n"
        ).encode()
        sock.sendall(request)

        sock.recv(256)
        sock.close()
    except Exception:

        pass

def _padding_loop() -> None:
    log.info("Traffic padding started (interval %d–%d s, burst %d–%d).",
             MIN_INTERVAL, MAX_INTERVAL, MIN_BURST, MAX_BURST)
    while not _stop_event.is_set():
        delay = random.uniform(MIN_INTERVAL, MAX_INTERVAL)
        _stop_event.wait(timeout=delay)
        if _stop_event.is_set():
            break

        burst = random.randint(MIN_BURST, MAX_BURST)
        for url in random.choices(TARGETS, k=burst):
            if _stop_event.is_set():
                break
            _http_head(url)
            log.debug("Padding → %s", url)
            _stop_event.wait(timeout=random.uniform(0.5, 3.0))

def start() -> threading.Thread:
    t = threading.Thread(target=_padding_loop, name="traffic-padding", daemon=True)
    t.start()
    return t

def stop() -> None:
    _stop_event.set()

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s")
    log.info("Running padding in foreground — Ctrl-C to stop.")
    try:
        start().join()
    except KeyboardInterrupt:
        stop()
