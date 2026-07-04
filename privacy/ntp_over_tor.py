

import logging
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import _path
from platform_utils import disable_system_ntp, block_ntp_port, is_admin

log = logging.getLogger(__name__)

SOCKS_HOST = "127.0.0.1"
SOCKS_PORT  = 9050
TIMEOUT_S   = 15

TIME_SOURCES: list[str] = [
    "https://www.cloudflare.com/",
    "https://www.google.com/",
    "https://duckduckgo.com/",
    "https://www.torproject.org/",
]

def _fetch_time_via_tor(url: str) -> datetime | None:
    curl_bin = shutil.which("curl")
    if not curl_bin:
        return None
    result = subprocess.run(
        [
            curl_bin, "-sI", "--max-time", str(TIMEOUT_S),
            "--socks5-hostname", f"{SOCKS_HOST}:{SOCKS_PORT}",
            url,
        ],
        capture_output=True, text=True,
    )
    for line in result.stdout.splitlines():
        if line.lower().startswith("date:"):
            date_str = line.split(":", 1)[1].strip()
            try:
                return datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S %Z").replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                pass
    return None

def sync_time() -> bool:
    timestamps: list[float] = []
    for url in TIME_SOURCES:
        dt = _fetch_time_via_tor(url)
        if dt:
            timestamps.append(dt.timestamp())
            log.debug("Time from %s: %s", url, dt.isoformat())

    if not timestamps:
        log.error("Could not fetch time from any source via Tor.")
        return False

    timestamps.sort()
    median_ts = timestamps[len(timestamps) // 2]
    dt_utc = datetime.fromtimestamp(median_ts, tz=timezone.utc)

    if sys.platform == "darwin":
        date_str = dt_utc.strftime("%m%d%H%M%Y.%S")
        result = subprocess.run(["date", date_str], capture_output=True, text=True)
    elif sys.platform == "win32":
        result = subprocess.run(
            ["powershell", "-Command",
             f"Set-Date -Date '{dt_utc.strftime('%Y-%m-%d %H:%M:%S')}'"],
            capture_output=True, text=True,
        )
    else:
        date_str = dt_utc.strftime("%Y-%m-%d %H:%M:%S")
        result = subprocess.run(["date", "-s", date_str], capture_output=True, text=True)
    if result.returncode != 0:
        log.error("date command failed: %s", result.stderr.strip())
        return False

    log.info("System clock set to %s (via Tor, median of %d sources).",
             dt_utc.isoformat(), len(timestamps))
    return True

def activate() -> None:
    if not is_admin():
        log.error("ntp_over_tor.activate() requires elevated privileges.")
        return
    disable_system_ntp()
    block_ntp_port()
    log.info("System NTP disabled and port 123 blocked.")
    sync_time()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    if not is_admin():
        if sys.platform == "win32":
            log.error("Please run from an Administrator shell.")
            sys.exit(1)
        os.execvp("sudo", ["sudo", sys.executable] + sys.argv)
    activate()
