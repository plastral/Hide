

import logging
import os
import re
import subprocess
import sys
from pathlib import Path

import _path
from platform_utils import IS_MACOS, real_uid_gid

log = logging.getLogger(__name__)

def _run(cmd: list[str], uid: int | None = None, gid: int | None = None) -> subprocess.CompletedProcess:
    kwargs: dict = dict(capture_output=True, text=True)
    if uid is not None and gid is not None:
        kwargs["preexec_fn"] = lambda: (os.setgid(gid), os.setuid(uid))
    return subprocess.run(cmd, **kwargs)

def installed_tor_version(uid: int, gid: int) -> str | None:
    result = _run(["brew", "list", "--versions", "tor"], uid, gid)
    if result.returncode != 0:
        return None

    match = re.search(r"tor\s+([\d.]+)", result.stdout)
    return match.group(1) if match else None

def latest_tor_version(uid: int, gid: int) -> str | None:
    result = _run(["brew", "info", "--json=v2", "tor"], uid, gid)
    if result.returncode != 0:
        return None
    import json
    try:
        data = json.loads(result.stdout)
        formulae = data.get("formulae", [])
        if formulae:
            return formulae[0].get("versions", {}).get("stable")
    except (json.JSONDecodeError, IndexError, KeyError):
        pass
    return None

def _version_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v))

def check_and_upgrade(uid: int | None = None, gid: int | None = None) -> bool:
    if not IS_MACOS:
        log.info("Tor Homebrew update check skipped on this platform.")
        return True
    detected_uid, detected_gid = real_uid_gid()
    real_uid = uid if uid is not None else detected_uid
    real_gid = gid if gid is not None else detected_gid

    installed = installed_tor_version(real_uid, real_gid)
    if installed is None:
        log.warning("Tor does not appear to be installed via Homebrew.")
        return False

    latest = latest_tor_version(real_uid, real_gid)
    if latest is None:
        log.warning("Could not determine latest Tor version — skipping update check.")
        return True

    log.info("Tor installed: %s  latest: %s", installed, latest)

    if _version_tuple(latest) <= _version_tuple(installed):
        log.info("Tor is up to date.")
        return True

    log.info("Upgrading Tor %s → %s ...", installed, latest)
    result = _run(["brew", "upgrade", "tor"], real_uid, real_gid)
    if result.returncode == 0:
        log.info("Tor upgraded successfully.")
        return True
    else:
        log.error("brew upgrade tor failed:\n%s", result.stderr.strip())
        return False

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    uid, gid = real_uid_gid()
    ok = check_and_upgrade(uid, gid)
    sys.exit(0 if ok else 1)
