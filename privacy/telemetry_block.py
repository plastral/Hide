

import logging
import os
import subprocess
import sys
from pathlib import Path

import _path
from platform_utils import (
    IS_MACOS,
    apply_hosts_block,
    macos_pf_flush_anchor,
    macos_pf_load_anchor,
    remove_hosts_block,
    is_admin,
)

log = logging.getLogger(__name__)

PF_ANCHOR  = "com.privacy_tool.telemetry"

TELEMETRY_DOMAINS: list[str] = [

    "gateway.icloud.com",
    "configuration.apple.com",
    "gsp-ssl.ls.apple.com",
    "gsp.apple.com",
    "gspe1-ssl.ls.apple.com",
    "gspe35-ssl.ls.apple.com",
    "api.smoot.apple.com",
    "pancake.apple.com",
    "suggestionsapi.apple.com",
    "swscan.apple.com",
    "swquery.apple.com",
    "swdist.apple.com",
    "ocsp.apple.com",
    "ocsp2.apple.com",
    "certs.apple.com",
    "valid.apple.com",
    "iadsdk.apple.com",
    "iad.apple.com",
    "metrics.apple.com",
    "xp.apple.com",
    "feedbackws.icloud.com",
    "idiagnostics.apple.com",
    "diagassets.apple.com",
    "radarsubmissions.apple.com",
    "crashes.apple.com",
    "analytics.apple.com",
    "securemetrics.apple.com",

    "ls.apple.com",
    "api.apple-cloudkit.com",
    "guzzoni.apple.com",

    "gdmf.apple.com",
    "appldnld.apple.com",

    "google-analytics.com",
    "www.google-analytics.com",
    "ssl.google-analytics.com",
    "analytics.google.com",
    "stats.g.doubleclick.net",

    "telemetry.mozilla.org",
    "incoming.telemetry.mozilla.org",
    "data.mozilla.com",
    "crash-stats.mozilla.com",
    "normandy.cdn.mozilla.net",
    "safebrowsing.google.com",
    "safebrowsing-cache.google.com",

    "p3a.brave.com",
    "p2a.brave.com",
    "variations.brave.com",
]

TELEMETRY_CIDRS: list[str] = [
    "17.249.0.0/16",
    "17.250.0.0/16",
    "17.188.0.0/16",
]

PF_TELEMETRY_RULES = "\n".join(
    f'  block drop out quick proto {{tcp udp}} from any to {cidr}'
    for cidr in TELEMETRY_CIDRS
) + "\n"

def apply_pf_block() -> None:
    if not IS_MACOS:
        return
    proc = macos_pf_load_anchor(PF_ANCHOR, PF_TELEMETRY_RULES)
    if proc.returncode != 0:
        log.error("pfctl telemetry anchor error: %s", proc.stderr.strip())
    log.info("Telemetry pfctl anchor loaded (%d CIDRs).", len(TELEMETRY_CIDRS))

def remove_pf_block() -> None:
    if not IS_MACOS:
        return
    macos_pf_flush_anchor(PF_ANCHOR)
    log.info("Telemetry pfctl anchor removed.")

def activate() -> None:
    if not is_admin():
        log.error("telemetry_block.activate() requires elevated privileges.")
        return
    apply_hosts_block(TELEMETRY_DOMAINS)
    apply_pf_block()
    log.info("Telemetry blocking active.")

def deactivate() -> None:
    if not is_admin():
        log.error("telemetry_block.deactivate() requires elevated privileges.")
        return
    remove_hosts_block()
    remove_pf_block()
    log.info("Telemetry blocking deactivated.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    if not is_admin():
        if sys.platform == "win32":
            log.error("Please run from an Administrator shell.")
            sys.exit(1)
        os.execvp("sudo", ["sudo", sys.executable] + sys.argv)
    activate()
