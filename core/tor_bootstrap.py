                      

import logging
import re
import socket
import time
from pathlib import Path

import _path
from platform_utils import app_support_dir
from config_loader import CFG

log = logging.getLogger(__name__)

_tor = CFG["tor"]

APP_SUPPORT       = app_support_dir()
LOG_PATH          = APP_SUPPORT / "tor.log"
SOCKS_HOST        = _tor["socks_host"]
SOCKS_PORT        = _tor["socks_port"]
BOOTSTRAP_TIMEOUT = _tor["bootstrap_timeout_s"]
POLL_INTERVAL     = _tor["bootstrap_poll_s"]

_BOOTSTRAP_RE = re.compile(r"Bootstrapped\s+(\d+)%", re.IGNORECASE)

def _socks_reachable() -> bool:
    try:
        with socket.create_connection((SOCKS_HOST, SOCKS_PORT), timeout=3):
            return True
    except OSError:
        return False

def wait_for_bootstrap(
    timeout_s: int = BOOTSTRAP_TIMEOUT,
    log_path: Path = LOG_PATH,
) -> bool:
    deadline  = time.monotonic() + timeout_s
    last_pct  = 0

    file_pos = 0
    if log_path.exists():
        file_pos = log_path.stat().st_size

    while time.monotonic() < deadline:

        if log_path.exists():
            try:
                with open(log_path, "r", errors="replace") as fh:
                    fh.seek(file_pos)
                    new_text = fh.read()
                    file_pos = fh.tell()
            except OSError:
                new_text = ""

            for m in _BOOTSTRAP_RE.finditer(new_text):
                pct = int(m.group(1))
                if pct != last_pct:
                    log.info("Tor connecting to the network: %d%%", pct)
                    last_pct = pct

        if last_pct >= 100 and _socks_reachable():
            log.info("Tor is fully connected and ready to accept connections.")
            return True

        if last_pct == 0 and _socks_reachable():
            log.info("SOCKS port is responding — treating Tor as ready.")
            return True

        time.sleep(POLL_INTERVAL)

    log.error(
        "Tor did not finish connecting within %ds (last progress seen: %d%%).",
        timeout_s, last_pct,
    )
    return False

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    raise SystemExit(0 if wait_for_bootstrap() else 1)
