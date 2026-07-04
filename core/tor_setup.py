

import os
import shutil
import subprocess
import sys
import logging
from pathlib import Path

log = logging.getLogger(__name__)

OBFS4_BRIDGES: list[str] = [
]

import _path
from platform_utils import IS_MACOS, app_support_dir, install_package
APP_SUPPORT  = app_support_dir()
TOR_DATA_DIR = APP_SUPPORT / "tor_data"
TORRC_PATH   = APP_SUPPORT / "torrc"
LOG_PATH     = APP_SUPPORT / "tor.log"

def _load_cfg() -> dict:
    try:
        import _path
        from config_loader import CFG
        return CFG
    except Exception:
        return {}

def brew_installed() -> bool:
    return shutil.which("brew") is not None

def install_brew() -> None:
    log.info("Installing Homebrew...")
    subprocess.run(
        '/bin/bash -c "$(curl -fsSL '
        'https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"',
        shell=True, check=True,
    )

def brew_install(package: str) -> None:
    r = subprocess.run(["brew", "list", "--formula", package], capture_output=True, text=True)
    if r.returncode == 0:
        log.info("%s is already installed — skipping.", package)
        return
    log.info("Installing %s via Homebrew...", package)
    subprocess.run(["brew", "install", package], check=True)

def obfs4proxy_path() -> str:
    for binary in ("obfs4proxy", "lyrebird", "obfs4proxy.exe", "lyrebird.exe"):
        path = shutil.which(binary)
        if path:
            return path
    unix_candidates = [
        "/opt/homebrew/bin/obfs4proxy", "/usr/local/bin/obfs4proxy", "/usr/bin/obfs4proxy",
        "/opt/homebrew/bin/lyrebird", "/usr/local/bin/lyrebird",
    ]
    for candidate in unix_candidates:
        if os.path.isfile(candidate):
            return candidate
    if sys.platform == "win32":
        localappdata = os.environ.get("LOCALAPPDATA", "")
        win_base = Path(localappdata) / "HIDE" / "tor"
        if win_base.exists():
            for name in ("obfs4proxy.exe", "lyrebird.exe"):
                found = next(win_base.rglob(name), None)
                if found:
                    return str(found)
    raise FileNotFoundError("obfs4proxy/lyrebird not found.")

_ISOLATION = "IsolateClientAddr IsolateDestPort IsolateDestAddr"

def write_torrc() -> None:
    APP_SUPPORT.mkdir(parents=True, exist_ok=True)
    TOR_DATA_DIR.mkdir(parents=True, exist_ok=True)

    cfg     = _load_cfg()
    tor_cfg = cfg.get("tor", {})

    exit_nodes         = tor_cfg.get("exit_nodes", "")
    exclude_exit_nodes = tor_cfg.get("exclude_exit_nodes", "")

    num_entry_guards      = tor_cfg.get("num_entry_guards", 3)
    max_circuit_dirtiness = tor_cfg.get("max_circuit_dirtiness_s", 600)

    def _p(path: Path) -> str:
        s = str(path).replace("\\", "/")
        return f'"{s}"' if " " in s else s

    lines: list[str] = [
        f"DataDirectory {_p(TOR_DATA_DIR)}",
        f"Log notice file {_p(LOG_PATH)}",
        f"SocksPort 9050 {_ISOLATION}",
        f"SocksPort 9150 {_ISOLATION}",
        f"SocksPort 9250 {_ISOLATION}",
        "SocksPolicy accept 127.0.0.1",
        "ControlPort 9051",
        "CookieAuthentication 1",
        f"NumEntryGuards {num_entry_guards}",
        f"MaxCircuitDirtiness {max_circuit_dirtiness}",
        "GuardLifetime 3 months",
    ]

    if sys.platform == "win32":
        # Windows has no pf/iptables to redirect :53 -> :5300, so Tor must
        # listen on the standard DNS port directly. Adapters are then pointed
        # at 127.0.0.1 (see platform_utils._windows_dns_redirect). Without this
        # the DNS redirect would send every lookup to a port nothing answers on,
        # breaking all name resolution on the machine.
        lines += ["DNSPort 127.0.0.1:53", "AutomapHostsOnResolve 1"]
    else:
        lines += ["DNSPort 5300", "AutomapHostsOnResolve 1"]

    if exit_nodes:
        lines += [
            f"ExitNodes {exit_nodes}",
            "StrictNodes 1",
        ]
    if exclude_exit_nodes:
        lines += [
            f"ExcludeExitNodes {exclude_exit_nodes}",
        ]

    try:
        obfs4_bin = obfs4proxy_path()
        safe_bin  = obfs4_bin.replace("\\", "/")
        safe_bin  = f'"{safe_bin}"' if " " in safe_bin else safe_bin
        lines += [f"ClientTransportPlugin obfs4 exec {safe_bin}"]
    except FileNotFoundError:
        log.warning("obfs4proxy not found — torrc written without bridge transport plugin.")


    if OBFS4_BRIDGES:
        lines += ["UseBridges 1"]
        for bridge in OBFS4_BRIDGES:
            lines.append(f"Bridge {bridge}")
    else:
        lines += ["UseBridges 0"]

    TORRC_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log.info("torrc written to %s", TORRC_PATH)

def _find_tor_bin() -> str:
    path = shutil.which("tor") or shutil.which("tor.exe")
    if path:
        return path
    if sys.platform == "win32":
        import os as _os
        win_base = Path(_os.environ.get("LOCALAPPDATA", "")) / "HIDE" / "tor"
        found = next(win_base.rglob("tor.exe"), None) if win_base.exists() else None
        if found:
            return str(found)
    raise FileNotFoundError("tor binary not found.")

def start_tor() -> subprocess.Popen:
    tor_bin = _find_tor_bin()
    proc = subprocess.Popen(
        [tor_bin, "-f", str(TORRC_PATH)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    log.info("Tor started (PID %d)", proc.pid)
    return proc

def setup() -> None:
    if IS_MACOS and not brew_installed():
        install_brew()
    install_package("tor", "tor")
    install_package("obfs4proxy", "obfs4proxy")
    write_torrc()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    setup()
