                      

import json
import logging
import shutil
from pathlib import Path

import _path
from platform_utils import IS_MACOS, IS_LINUX, IS_WINDOWS

log = logging.getLogger(__name__)

HOME = Path.home()

FIREFOX_USER_JS = """

user_pref("media.peerconnection.enabled", false);
user_pref("media.peerconnection.use_document_iceservers", false);
user_pref("media.peerconnection.video.enabled", false);
user_pref("media.peerconnection.identity.enabled", false);

user_pref("media.peerconnection.ice.default_address_only", true);
user_pref("media.peerconnection.ice.no_host", true);
user_pref("media.peerconnection.ice.proxy_only", true);
user_pref("media.peerconnection.ice.proxy_only_if_behind_proxy", true);

user_pref("privacy.resistFingerprinting", true);
user_pref("privacy.resistFingerprinting.block_mozAddonManager", true);

user_pref("dom.battery.enabled", false);

user_pref("general.useragent.override", "");

user_pref("webgl.disabled", true);
user_pref("webgl.enable-webgl2", false);

user_pref("geo.enabled", false);

user_pref("privacy.spoof_english", 2);

user_pref("media.navigator.enabled", false);
user_pref("media.navigator.video.enabled", false);
user_pref("media.device.microphone.enabled", false);

user_pref("network.trr.mode", 5);  // 5 = disabled (we handle DNS at OS level)

user_pref("network.proxy.type", 1);
user_pref("network.proxy.socks", "127.0.0.1");
user_pref("network.proxy.socks_port", 9150);
user_pref("network.proxy.socks_version", 5);
user_pref("network.proxy.socks_remote_dns", true);
user_pref("network.proxy.no_proxies_on", "");
""".strip()

def _firefox_profile_dirs() -> list[Path]:
    profiles: list[Path] = []
    bases: list[Path] = []
    if IS_MACOS:
        bases = [
            HOME / "Library" / "Application Support" / "Firefox" / "Profiles",
            HOME / "Library" / "Application Support" / "Firefox",
        ]
    elif IS_LINUX:
        bases = [HOME / ".mozilla" / "firefox"]
    elif IS_WINDOWS:
        appdata = Path(shutil.os.environ.get("APPDATA", HOME)) if hasattr(shutil, "os") else HOME
        import os as _os
        appdata = Path(_os.environ.get("APPDATA", str(HOME)))
        bases = [appdata / "Mozilla" / "Firefox" / "Profiles"]

    for base in bases:
        if not base.exists():
            continue
        for entry in base.iterdir():
            if entry.is_dir() and (entry / "prefs.js").exists():
                profiles.append(entry)
    return profiles

def apply_firefox() -> int:
    profiles = _firefox_profile_dirs()
    if not profiles:
        log.info("No Firefox profiles found — skipping.")
        return 0
    for profile in profiles:
        target = profile / "user.js"
        target.write_text(FIREFOX_USER_JS + "\n", encoding="utf-8")
        log.info("Firefox user.js written: %s", profile.name)
    return len(profiles)

CHROMIUM_POLICY = {
    "WebRtcIPHandling": "disable_non_proxied_udp",
    "WebRtcUDPPortRange": "10000-10001",
    "DnsOverHttpsMode": "off",
    "ProxySettings": {
        "ProxyMode": "fixed_servers",
        "ProxyServer": "socks5://127.0.0.1:9150",
        "ProxyBypassList": "",
    },
}

import os as _os
_APPDATA = Path(_os.environ.get("APPDATA", str(HOME)))

CHROMIUM_POLICY_PATHS: dict[str, Path] = {}
if IS_MACOS:
    CHROMIUM_POLICY_PATHS = {
        "Chrome":   HOME / "Library" / "Application Support" / "Google" / "Chrome" / "policies" / "managed",
        "Chromium": HOME / "Library" / "Application Support" / "Chromium" / "policies" / "managed",
        "Brave":    HOME / "Library" / "Application Support" / "BraveSoftware" / "Brave-Browser" / "policies" / "managed",
    }
elif IS_LINUX:
    CHROMIUM_POLICY_PATHS = {
        "Chrome":   HOME / ".config" / "google-chrome" / "policies" / "managed",
        "Chromium": HOME / ".config" / "chromium" / "policies" / "managed",
        "Brave":    HOME / ".config" / "BraveSoftware" / "Brave-Browser" / "policies" / "managed",
    }
elif IS_WINDOWS:
    CHROMIUM_POLICY_PATHS = {
        "Chrome":   Path(r"C:\Program Files\Google\Chrome\Application\policies\managed"),
        "Chromium": _APPDATA / "Chromium" / "policies" / "managed",
        "Brave":    Path(r"C:\Program Files\BraveSoftware\Brave-Browser\Application\policies\managed"),
    }

def apply_chromium_family() -> int:
    written = 0
    for name, policy_dir in CHROMIUM_POLICY_PATHS.items():
        app_dir = policy_dir.parent.parent
        if not app_dir.exists():
            continue
        policy_dir.mkdir(parents=True, exist_ok=True)
        policy_file = policy_dir / "privacy_tool.json"
        policy_file.write_text(
            json.dumps(CHROMIUM_POLICY, indent=2), encoding="utf-8"
        )
        log.info("%s managed policy written: %s", name, policy_file)
        written += 1
    if written == 0:
        log.info("No Chromium-family browsers found — skipping.")
    return written

def apply_all() -> None:
    fx = apply_firefox()
    cr = apply_chromium_family()
    log.info(
        "WebRTC prevention applied — Firefox profiles: %d, Chromium browsers: %d",
        fx, cr,
    )

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    apply_all()
