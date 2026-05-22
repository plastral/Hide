                      

import logging
import os
import re
import secrets
import subprocess
import sys
import time
from pathlib import Path

import _path
from platform_utils import app_support_dir

APP_SUPPORT = app_support_dir()
MAX_AGE_HOURS = 24

LOG_FILES = [
    APP_SUPPORT / "main.log",
    APP_SUPPORT / "killswitch.log",
    APP_SUPPORT / "tor.log",
    APP_SUPPORT / "bridge_refresh.log",
    APP_SUPPORT / "launchd_stdout.log",
    APP_SUPPORT / "launchd_stderr.log",
]

_TOR_TS = re.compile(
    r"^[A-Z][a-z]{2}\s+\d{1,2}\s+(\d{2}):(\d{2}):(\d{2})\.\d+"
)
_ISO_TS = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

def _line_age_hours(line: str, now: float) -> float | None:
    m = _ISO_TS.match(line)
    if m:
        try:
            import datetime
            ts = datetime.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
            return (now - ts.timestamp()) / 3600
        except ValueError:
            pass

    m2 = _TOR_TS.match(line)
    if m2:
        h, mi, s = int(m2.group(1)), int(m2.group(2)), int(m2.group(3))
        import datetime
        today = datetime.date.today()
        candidate = datetime.datetime(today.year, today.month, today.day, h, mi, s)
        age = (now - candidate.timestamp()) / 3600
        if age < 0:
            age += 24                          
        return age
    return None

def _secure_overwrite(path: Path, size: int) -> None:
    if size == 0:
        return
    with open(path, "r+b") as f:
        f.seek(0)

        for _ in range(3):
            f.seek(0)
            f.write(secrets.token_bytes(size))
            f.flush()
            os.fsync(f.fileno())
        f.truncate(0)

def purge_file(path: Path, max_age_hours: float = MAX_AGE_HOURS) -> int:
    if not path.exists() or path.stat().st_size == 0:
        return 0

    now = time.time()
    original = path.read_text(errors="replace")
    lines = original.splitlines(keepends=True)

    kept: list[str] = []
    removed = 0
    for line in lines:
        age = _line_age_hours(line, now)
        if age is None or age <= max_age_hours:
            kept.append(line)
        else:
            removed += 1

    if removed == 0:
        return 0

    freed_bytes = len(original.encode()) - sum(len(l.encode()) for l in kept)

    new_content = "".join(kept).encode()
    with open(path, "r+b") as f:
        f.write(new_content)

        if freed_bytes > 0:
            for _ in range(3):
                f.seek(len(new_content))
                f.write(secrets.token_bytes(freed_bytes))
                f.flush()
                os.fsync(f.fileno())
        f.truncate(len(new_content))

    log.info("%-50s  removed %d line(s), freed ~%d bytes", str(path), removed, freed_bytes)
    return removed

def purge_tor_data_dir() -> None:
    tor_data = APP_SUPPORT / "tor_data"
    if not tor_data.is_dir():
        return
    cutoff = time.time() - 48 * 3600
    for f in tor_data.rglob("*"):
        if f.is_file() and f.stat().st_mtime < cutoff:
            try:
                _secure_overwrite(f, f.stat().st_size)
                f.unlink()
                log.info("Purged stale Tor descriptor: %s", f.name)
            except OSError as exc:
                log.warning("Could not purge %s: %s", f, exc)

def run() -> None:
    log.info("=== Log purge started ===")
    total = 0
    for log_file in LOG_FILES:
        total += purge_file(log_file)
    purge_tor_data_dir()
    log.info("=== Log purge complete — %d line(s) removed ===", total)

if __name__ == "__main__":
    run()
