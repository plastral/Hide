                      

import logging
import os
import subprocess
import sys
from pathlib import Path

import _path
from platform_utils import apply_hosts_block, remove_hosts_block, IS_MACOS

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

PF_TELEMETRY_RULES = f"""
anchor "{PF_ANCHOR}" {{
""" + "\n".join(
    f'  block drop out quick proto {{tcp udp}} from any to {cidr}'
    for cidr in TELEMETRY_CIDRS
) + """
}
"""

def apply_pf_block() -> None:
    if not IS_MACOS:
        return
    proc = subprocess.run(
        ["pfctl", "-f", "-"],
        input=PF_TELEMETRY_RULES,
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        log.error("pfctl telemetry anchor error: %s", proc.stderr.strip())
    subprocess.run(["pfctl", "-e"], capture_output=True)
    log.info("Telemetry pfctl anchor loaded (%d CIDRs).", len(TELEMETRY_CIDRS))

def remove_pf_block() -> None:
    if not IS_MACOS:
        return
    subprocess.run(
        ["pfctl", "-a", PF_ANCHOR, "-F", "all"],
        capture_output=True,
    )
    log.info("Telemetry pfctl anchor removed.")

def activate() -> None:
    if os.geteuid() != 0:
        log.error("telemetry_block.activate() requires root.")
        return
    apply_hosts_block(TELEMETRY_DOMAINS)
    apply_pf_block()
    log.info("Telemetry blocking active.")

def deactivate() -> None:
    if os.geteuid() != 0:
        log.error("telemetry_block.deactivate() requires root.")
        return
    remove_hosts_block()
    remove_pf_block()
    log.info("Telemetry blocking deactivated.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    if os.geteuid() != 0:
        os.execvp("sudo", ["sudo", sys.executable] + sys.argv)
    activate()
