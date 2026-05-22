                      

import logging
import os
import subprocess
import sys
from pathlib import Path

import _path
from platform_utils import app_support_dir, IS_MACOS, IS_LINUX, IS_WINDOWS

log = logging.getLogger(__name__)

APP_SUPPORT    = app_support_dir()
TZ_BACKUP_FILE = APP_SUPPORT / "original_timezone.txt"
TARGET_TZ      = "UTC"

def get_current_timezone() -> str:
    if IS_MACOS:
        r = subprocess.run(
            ["systemsetup", "-gettimezone"],
            capture_output=True, text=True,
        )
        line = r.stdout.strip()
        if ":" in line:
            return line.split(":", 1)[1].strip()
        return "UTC"
    elif IS_LINUX:
        r = subprocess.run(
            ["timedatectl", "show", "--property=Timezone", "--value"],
            capture_output=True, text=True,
        )
        return r.stdout.strip() or "UTC"
    elif IS_WINDOWS:
        r = subprocess.run(["tzutil", "/g"], capture_output=True, text=True)
        return r.stdout.strip() or "UTC"
    return "UTC"

def set_timezone(tz: str) -> bool:
    if IS_MACOS:
        r = subprocess.run(
            ["sudo", "systemsetup", "-settimezone", tz],
            capture_output=True, text=True,
        )
    elif IS_LINUX:
        r = subprocess.run(
            ["sudo", "timedatectl", "set-timezone", tz],
            capture_output=True, text=True,
        )
    elif IS_WINDOWS:
        r = subprocess.run(
            ["tzutil", "/s", tz],
            capture_output=True, text=True,
        )
    else:
        log.error("set_timezone: unsupported platform.")
        return False

    if r.returncode != 0:
        log.error("Could not set timezone to %s: %s", tz, r.stderr.strip())
        return False
    log.info("Timezone set to %s.", tz)
    return True

def activate() -> bool:
    current = get_current_timezone()
    if current.upper() in ("UTC", "GMT", "ETC/UTC", "ETC/GMT", "COORDINATED UNIVERSAL TIME"):
        log.info("Timezone already UTC — no change needed.")
        return True

    APP_SUPPORT.mkdir(parents=True, exist_ok=True)
    TZ_BACKUP_FILE.write_text(current, encoding="utf-8")
    log.info("Original timezone saved: %s", current)

    return set_timezone(TARGET_TZ)

def deactivate() -> bool:
    if not TZ_BACKUP_FILE.exists():
        log.info("No timezone backup found — nothing to restore.")
        return True

    original = TZ_BACKUP_FILE.read_text(encoding="utf-8").strip()
    if not original:
        return True

    ok = set_timezone(original)
    if ok:
        TZ_BACKUP_FILE.unlink(missing_ok=True)
        log.info("Timezone restored to %s.", original)
    return ok

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "restore":
        deactivate()
    else:
        print(f"Current timezone: {get_current_timezone()}")
        activate()
