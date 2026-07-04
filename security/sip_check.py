

import logging
import subprocess
from pathlib import Path

import _path

log = logging.getLogger(__name__)

def get_sip_status() -> str:
    try:
        r = subprocess.run(
            ["csrutil", "status"],
            capture_output=True, text=True, timeout=5,
        )
        output = (r.stdout + r.stderr).lower()
        if "enabled" in output:
            return "enabled"
        if "disabled" in output:
            return "disabled"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return "unknown"

def check(warn_only: bool = True) -> bool:
    from platform_utils import IS_MACOS
    if not IS_MACOS:

        return True

    status = get_sip_status()

    if status == "enabled":
        log.info("SIP is enabled — system files are protected against tampering.")
        return True

    if status == "disabled":
        log.critical(
            "SIP IS DISABLED — System Integrity Protection is off.\n"
            "  A local attacker can modify system binaries, inject kernel\n"
            "  extensions, and bypass all privacy protections in this tool.\n"
            "  To enable SIP: reboot into Recovery Mode (hold ⌘R at startup),\n"
            "  open Terminal, and run: csrutil enable"
        )
        return False

    log.warning("Could not determine SIP status — csrutil may be unavailable.")
    return True

def enforce(halt_on_disabled: bool = False) -> bool:
    ok = check()
    if not ok and halt_on_disabled:
        import sys
        sys.exit(3)
    return ok

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    status = get_sip_status()
    print(f"SIP status: {status}")
    enforce(halt_on_disabled=False)
