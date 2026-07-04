

import logging
import os
import subprocess
import sys
from pathlib import Path

import _path
from platform_utils import firewall_block_dns, firewall_restore_dns, IS_MACOS, is_admin

log = logging.getLogger(__name__)

DNS_ANCHOR   = "com.privacy_tool.dns"
TOR_DNS_PORT = 5300

RESOLVER_DIR  = Path("/etc/resolver")
RESOLVER_FILE = RESOLVER_DIR / "privacy_tool_dns"

def _write_resolver_override() -> None:
    RESOLVER_DIR.mkdir(parents=True, exist_ok=True)
    RESOLVER_FILE.write_text(f"nameserver 127.0.0.1\nport {TOR_DNS_PORT}\n")

def _remove_resolver_override() -> None:
    RESOLVER_FILE.unlink(missing_ok=True)

def _flush_dns_cache() -> None:
    if IS_MACOS:
        subprocess.run(["dscacheutil", "-flushcache"], capture_output=True)
        subprocess.run(["killall", "-HUP", "mDNSResponder"], capture_output=True)

def activate() -> None:
    if not is_admin():
        log.error("DNS leak prevention requires elevated privileges.")
        return
    firewall_block_dns()
    if IS_MACOS:
        _write_resolver_override()
    _flush_dns_cache()
    log.info("DNS and STUN leak prevention is now active.")

def deactivate() -> None:
    if not is_admin():
        log.error("DNS leak prevention requires elevated privileges.")
        return
    if IS_MACOS:
        _remove_resolver_override()
    firewall_restore_dns()
    _flush_dns_cache()
    log.info("DNS leak prevention has been deactivated.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    if not is_admin():
        if sys.platform == "win32":
            log.error("Please run from an Administrator shell.")
            sys.exit(1)
        os.execvp("sudo", ["sudo", sys.executable] + sys.argv)
    activate()
