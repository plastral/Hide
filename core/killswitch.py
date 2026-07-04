

import argparse
import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import _path
from platform_utils import app_support_dir, firewall_block, firewall_pass, is_admin

POLL_INTERVAL_S = 3

TOR_PROCESS_NAME = "tor"

SOCKS_HOST = "127.0.0.1"
SOCKS_PORT = 9050

LOG_PATH = app_support_dir() / "killswitch.log"

PF_ANCHOR = "com.privacy_tool.killswitch"

LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

def require_root() -> None:
    if not is_admin():
        log.error("killswitch.py must be run with elevated privileges.")
        sys.exit(1)

def activate_killswitch() -> None:
    log.warning("Tor went down — blocking all non-loopback traffic to prevent IP leaks.")
    firewall_block()

def deactivate_killswitch() -> None:
    log.info("Tor is back up — restoring normal traffic flow.")
    firewall_pass()

def tor_pid_from_file(pid_file: Path) -> int | None:
    try:
        return int(pid_file.read_text().strip())
    except (FileNotFoundError, ValueError):
        return None

def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False

def tor_running_by_name() -> bool:
    if sys.platform == "win32":
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq tor.exe"],
            capture_output=True, text=True,
        )
        return "tor.exe" in result.stdout.lower()
    result = subprocess.run(
        ["pgrep", "-x", TOR_PROCESS_NAME],
        capture_output=True, text=True,
    )
    return result.returncode == 0

def tor_socks_reachable() -> bool:
    import socket
    try:
        with socket.create_connection((SOCKS_HOST, SOCKS_PORT), timeout=2):
            return True
    except OSError:
        return False

def tor_is_healthy(pid_file: Path | None) -> bool:
    if pid_file:
        pid = tor_pid_from_file(pid_file)
        if pid is None or not pid_alive(pid):
            return False
    else:
        if not tor_running_by_name():
            return False

    return tor_socks_reachable()

_killswitch_active = False

def _cleanup(signum=None, frame=None) -> None:
    global _killswitch_active
    if _killswitch_active:
        log.info("Shutting down — removing traffic block before exit.")
        deactivate_killswitch()
    log.info("Kill-switch daemon stopped.")
    sys.exit(0)

def run(pid_file: Path | None) -> None:
    global _killswitch_active

    signal.signal(signal.SIGTERM, _cleanup)
    signal.signal(signal.SIGINT, _cleanup)

    log.info(
        "Kill-switch daemon started. Checking every %ds. PID file: %s",
        POLL_INTERVAL_S,
        pid_file or "none (falling back to process name search)",
    )

    while True:
        healthy = tor_is_healthy(pid_file)

        if not healthy and not _killswitch_active:
            activate_killswitch()
            _killswitch_active = True
        elif healthy and _killswitch_active:
            deactivate_killswitch()
            _killswitch_active = False

        time.sleep(POLL_INTERVAL_S)

if __name__ == "__main__":
    require_root()

    parser = argparse.ArgumentParser(description="Network kill-switch daemon")
    parser.add_argument(
        "--pid-file",
        type=Path,
        default=None,
        help="Path to Tor's PID file (e.g. /var/run/tor/tor.pid)",
    )
    args = parser.parse_args()

    run(args.pid_file)
