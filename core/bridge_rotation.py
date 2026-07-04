

import json
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import _path
import tor_setup

log = logging.getLogger(__name__)

MOAT_URL = "https://bridges.torproject.org/moat/circumvention/builtin"
REQUEST_TIMEOUT_S = 15

FALLBACK_BRIDGES: list[str] = [
    "obfs4 192.95.36.142:443 CDF2E852BF539B82BD10E27E9115A31734E378C2 cert=qUVQ0srL1JI/vO6V6m/24anYXiJD3zP8bsEFyuh1qtUZktAjpQ/tsN4tKS9LE4SZVRuC4A iat-mode=0",
    "obfs4 38.229.1.78:80 C8CBDB2464FC9804A69531437BCF2BE31FDD2EE4 cert=Hmyfd2ev46gGY7NoVxkptipdzFQSY40w8zXABqLOzv1y9XL3/psggNvc90wh/09yBZA iat-mode=0",
    "obfs4 38.229.33.83:80 0BAC39417268B96B9F514E7F63FA6FBA1A788955 cert=VwEFpk9F/UN9JED7XpG1XOjm/O8KCXK2Roufz/omuuMwcCsp56gKU1mCYCfMDDfm8g iat-mode=0",
]

def fetch_bridges_from_moat() -> list[str]:
    payload = json.dumps({"transport": "obfs4"}).encode()
    req = urllib.request.Request(
        MOAT_URL,
        data=payload,
        headers={"Content-Type": "application/vnd.api+json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:
            body = json.loads(resp.read().decode())
    except (urllib.error.URLError, json.JSONDecodeError, OSError) as exc:
        log.warning("MOAT API unreachable: %s — using fallback bridges.", exc)
        return []

    bridges: list[str] = []

    for line in body.get("obfs4", []):
        line = line.strip()
        if line.startswith("obfs4 "):
            bridges.append(line)

    if not bridges:
        log.warning("MOAT returned no obfs4 bridges — using fallback bridges.")
    else:
        log.info("Fetched %d fresh bridge(s) from MOAT.", len(bridges))

    return bridges

def reload_tor() -> bool:
    result = subprocess.run(
        ["pgrep", "-x", "tor"], capture_output=True, text=True
    )
    if result.returncode != 0:
        log.warning("Tor is not running — skipping reload.")
        return False
    for pid_str in result.stdout.strip().splitlines():
        try:
            os.kill(int(pid_str), signal.SIGHUP)
            log.info("Sent SIGHUP to Tor PID %s.", pid_str)
        except (ValueError, ProcessLookupError) as exc:
            log.warning("Could not signal Tor PID %s: %s", pid_str, exc)
    return True

def rotate(force_fallback: bool = False) -> list[str]:
    bridges = [] if force_fallback else fetch_bridges_from_moat()

    if not bridges:
        bridges = FALLBACK_BRIDGES

    if not bridges:
        log.error("No bridges available (MOAT failed and no fallback configured).")
        return []

    original = tor_setup.OBFS4_BRIDGES
    tor_setup.OBFS4_BRIDGES = bridges
    try:
        tor_setup.write_torrc()
    finally:
        tor_setup.OBFS4_BRIDGES = original

    reload_tor()
    return bridges

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    written = rotate()
    if written:
        print(f"Active bridges ({len(written)}):")
        for b in written:
            print(f"  {b}")
