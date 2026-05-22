                      

import logging
import subprocess

import _path              

log = logging.getLogger(__name__)

def filevault_enabled() -> bool:
    try:
        r = subprocess.run(
            ["fdesetup", "status"],
            capture_output=True, text=True, timeout=10,
        )
        return "on" in r.stdout.lower()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False

def swap_encrypted() -> bool:

    try:
        r = subprocess.run(
            ["sysctl", "vm.compressor_mode"],
            capture_output=True, text=True, timeout=5,
        )

        if "4" in r.stdout:
            return True
    except Exception:
        pass

    return filevault_enabled()

def check() -> dict:
    from platform_utils import IS_MACOS
    if not IS_MACOS:
        return {"filevault": None, "swap_encrypted": None, "safe": True}

    fv  = filevault_enabled()
    swp = swap_encrypted()
    safe = fv and swp

    if not fv:
        log.warning(
            "FileVault is OFF — your disk and swap files are unencrypted.\n"
            "  Sensitive data (session tokens, browser history, Tor credentials)\n"
            "  could be recovered from disk after the machine shuts down.\n"
            "  Enable FileVault: System Settings → Privacy & Security → FileVault → Turn On"
        )
    elif not swp:
        log.warning(
            "Swap encryption could not be confirmed — FileVault is on but we\n"
            "  could not verify encrypted swap directly. This may be fine on\n"
            "  Apple Silicon, which uses hardware-backed swap encryption."
        )
    else:
        log.info("FileVault is on and swap is encrypted — disk data is protected.")

    return {"filevault": fv, "swap_encrypted": swp, "safe": safe}

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    result = check()
    print(f"FileVault: {'✓' if result['filevault'] else '✗'}")
    print(f"Swap encrypted: {'✓' if result['swap_encrypted'] else '✗'}")
    print(f"Safe: {'✓' if result['safe'] else '✗ — consider enabling FileVault'}")
