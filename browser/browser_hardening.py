                      

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

import _path
from platform_utils import app_support_dir

log = logging.getLogger(__name__)

HOME = Path.home()
PROFILE_BASE = app_support_dir() / "browser_profiles"

FIREFOX_PREFS = """

user_pref("privacy.resistFingerprinting", true);
user_pref("privacy.resistFingerprinting.block_mozAddonManager", true);

user_pref("privacy.resistFingerprinting.letterboxing", true);

user_pref("media.peerconnection.enabled", false);
user_pref("media.peerconnection.ice.no_host", true);
user_pref("media.peerconnection.ice.proxy_only", true);

user_pref("general.useragent.override", "Mozilla/5.0 (Windows NT 10.0; rv:109.0) Gecko/20100101 Firefox/115.0");

user_pref("dom.maxHardwareConcurrency", 2);

user_pref("dom.battery.enabled", false);
user_pref("dom.vr.enabled", false);
user_pref("device.sensors.enabled", false);

user_pref("webgl.disabled", true);
user_pref("webgl.enable-webgl2", false);

user_pref("canvas.capturestream.enabled", false);

user_pref("geo.enabled", false);
user_pref("geo.provider.use_corelocation", false);

user_pref("intl.accept_languages", "en-US, en");
user_pref("javascript.use_us_english_locale", true);

user_pref("media.navigator.enabled", false);
user_pref("media.navigator.video.enabled", false);

user_pref("toolkit.telemetry.enabled", false);
user_pref("toolkit.telemetry.unified", false);
user_pref("toolkit.telemetry.server", "");
user_pref("datareporting.healthreport.uploadEnabled", false);
user_pref("datareporting.policy.dataSubmissionEnabled", false);
user_pref("app.shield.optoutstudies.enabled", false);
user_pref("browser.crashReports.unsubmittedCheck.autoSubmit2", false);

user_pref("network.proxy.type", 1);
user_pref("network.proxy.socks", "127.0.0.1");
user_pref("network.proxy.socks_port", 9150);
user_pref("network.proxy.socks_version", 5);
user_pref("network.proxy.socks_remote_dns", true);
user_pref("network.proxy.no_proxies_on", "");

user_pref("network.trr.mode", 5);

user_pref("browser.safebrowsing.malware.enabled", false);
user_pref("browser.safebrowsing.phishing.enabled", false);
user_pref("browser.safebrowsing.downloads.enabled", false);
user_pref("browser.safebrowsing.downloads.remote.enabled", false);

user_pref("privacy.firstparty.isolate", true);

user_pref("network.prefetch-next", false);
user_pref("network.dns.disablePrefetch", true);
user_pref("network.predictor.enabled", false);
user_pref("browser.send_pings", false);
user_pref("network.http.speculative-parallel-limit", 0);

user_pref("privacy.donottrackheader.enabled", true);
""".strip()

def _find_firefox() -> str | None:
    for candidate in [

        "/Applications/Firefox.app/Contents/MacOS/firefox",

        "/usr/bin/firefox",
        "/snap/bin/firefox",
        str(HOME / ".local" / "bin" / "firefox"),

        r"C:\Program Files\Mozilla Firefox\firefox.exe",
        shutil.which("firefox"),
    ]:
        if candidate and os.path.isfile(candidate):
            return candidate
    return None

def launch_firefox() -> None:
    fx = _find_firefox()
    if not fx:
        log.error("Firefox not found. Install from https://www.mozilla.org/firefox/")
        sys.exit(1)

    profile_dir = PROFILE_BASE / "firefox"
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "user.js").write_text(FIREFOX_PREFS + "\n", encoding="utf-8")

    log.info("Launching hardened Firefox profile at %s", profile_dir)
    subprocess.Popen([
        fx,
        "--profile", str(profile_dir),
        "--no-remote",
        "--new-instance",
    ])

_CHROMIUM_BINS: dict[str, list[str]] = {
    "chromium": [
        shutil.which("chromium") or "",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
    ],
    "chrome": [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        shutil.which("google-chrome") or "",
        "/usr/bin/google-chrome",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    ],
    "brave": [
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        shutil.which("brave") or "",
        "/usr/bin/brave-browser",
        "/snap/bin/brave",
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    ],
}

_CHROMIUM_FLAGS = [

    "--proxy-server=socks5://127.0.0.1:9150",
    "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1",

    "--disable-webgl",
    "--disable-reading-from-canvas",
    "--no-pings",

    "--disable-background-networking",
    "--disable-sync",
    "--disable-translate",
    "--disable-extensions",
    "--disable-default-apps",
    "--disable-component-update",
    "--disable-client-side-phishing-detection",
    "--disable-hang-monitor",
    "--safebrowsing-disable-auto-update",
    "--metrics-recording-only",
    "--disable-breakpad",
    "--no-first-run",
    "--no-service-autorun",

    "--enforce-webrtc-ip-permission-check",
    "--webrtc-ip-handling-policy=disable_non_proxied_udp",
]

def launch_chromium(browser: str = "chromium") -> None:
    candidates = _CHROMIUM_BINS.get(browser, [])
    binary = next((c for c in candidates if c and os.path.isfile(c)), None)
    if not binary:
        log.error("%s binary not found.", browser.title())
        sys.exit(1)

    profile_dir = PROFILE_BASE / browser
    profile_dir.mkdir(parents=True, exist_ok=True)

    log.info("Launching hardened %s profile at %s", browser.title(), profile_dir)
    subprocess.Popen([binary, f"--user-data-dir={profile_dir}"] + _CHROMIUM_FLAGS)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    browsers = sys.argv[1:] or ["firefox"]
    for b in browsers:
        b = b.lower()
        if b == "firefox":
            launch_firefox()
        elif b in ("chromium", "chrome", "brave"):
            launch_chromium(b)
        else:
            print(f"Unknown browser: {b}. Options: firefox, chromium, chrome, brave")
            sys.exit(1)
