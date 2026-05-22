                      

import os
import re
import subprocess
import sys
import random
import logging
from typing import Optional

import _path
from platform_utils import (
    get_active_interfaces as _platform_get_active_interfaces,
    randomize_mac as _platform_randomize_mac,
    IS_MACOS,
)

log = logging.getLogger(__name__)

def require_root() -> None:
    if os.geteuid() != 0:
        args = ["sudo", sys.executable, __file__] + sys.argv[1:]
        os.execvp("sudo", args)
        sys.exit(1)

def random_mac() -> str:
    first = (random.randint(0x00, 0xFF) & 0xFE) | 0x02
    rest  = [random.randint(0x00, 0xFF) for _ in range(5)]
    return ":".join(f"{b:02x}" for b in [first] + rest)

def _interface_has_ip(iface: str) -> bool:
    if not IS_MACOS:
        return True
    r = subprocess.run(["ifconfig", iface], capture_output=True, text=True)
    return bool(re.search(r"\binet\s+\d+\.\d+\.\d+\.\d+", r.stdout))

def _default_route_interface() -> Optional[str]:
    if not IS_MACOS:
        return None
    r = subprocess.run(["route", "get", "default"], capture_output=True, text=True)
    m = re.search(r"interface:\s+(\S+)", r.stdout)
    return m.group(1) if m else None

def get_active_interfaces() -> list[str]:
    return _platform_get_active_interfaces()

def current_mac(interface: str) -> Optional[str]:
    if IS_MACOS:
        r = subprocess.run(["ifconfig", interface], capture_output=True, text=True)
        m = re.search(r"ether\s+([\da-f:]{17})", r.stdout)
        return m.group(1) if m else None
    return None

def set_mac(interface: str, mac: str) -> bool:
    if not IS_MACOS:
        log.debug("set_mac: macOS-specific path skipped on this platform.")
        return False
    try:

        r_type = subprocess.run(
            ["networksetup", "-listallhardwareports"],
            capture_output=True, text=True,
        )
        is_wifi = False
        prev_was_wifi = False
        for line in r_type.stdout.splitlines():
            if "Wi-Fi" in line:
                prev_was_wifi = True
            if prev_was_wifi and interface in line:
                is_wifi = True
                break

        if is_wifi:
            subprocess.run(
                ["networksetup", "-setairportpower", interface, "off"],
                capture_output=True,
            )

        subprocess.run(["ifconfig", interface, "down"], capture_output=True)
        result = subprocess.run(
            ["ifconfig", interface, "ether", mac],
            capture_output=True, text=True,
        )
        if result.returncode != 0:

            subprocess.run(["ifconfig", interface, "up"], capture_output=True)
            if is_wifi:
                subprocess.run(
                    ["networksetup", "-setairportpower", interface, "on"],
                    capture_output=True,
                )
            log.debug("ifconfig ether failed on %s: %s", interface, result.stderr.strip())
            return False

        subprocess.run(["ifconfig", interface, "up"], capture_output=True)
        if is_wifi:
            subprocess.run(
                ["networksetup", "-setairportpower", interface, "on"],
                capture_output=True,
            )
        log.debug("%s MAC → %s", interface, mac)
        return True

    except Exception as exc:
        log.debug("set_mac(%s) skipped: %s", interface, exc)
        return False

def randomize_all() -> tuple[int, int]:
    if os.geteuid() != 0:
        log.debug("MAC randomization skipped: not root.")
        return 0, 0
    interfaces = get_active_interfaces()
    ok_count = skipped = 0
    for iface in interfaces:
        new_mac = _platform_randomize_mac(iface)
        if new_mac:
            log.debug("%s MAC → %s", iface, new_mac)
            ok_count += 1
        else:
            skipped += 1
    return ok_count, skipped

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s")
    ok, skip = randomize_all()
    print(f"Done — {ok} randomized, {skip} skipped (inactive/unsupported)")
