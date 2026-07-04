

import json
import logging
import os
import platform
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

if sys.version_info < (3, 10):
    print("HIDE requires Python 3.10 or later.")
    sys.exit(1)

TOOL_DIR    = Path(__file__).parent

sys.path.insert(0, str(TOOL_DIR))
import _path
from process_utils import set_process_name, InstanceLock
from platform_utils import app_support_dir, real_uid_gid, user_home
APP_SUPPORT = app_support_dir()
USER_HOME = user_home()

set_process_name("HIDE")
DAEMON_DIR  = Path("/Library/LaunchDaemons")
AGENT_DIR   = USER_HOME / "Library" / "LaunchAgents"

LAUNCHD_DIR  = TOOL_DIR / "launchd"
ROOT_PLISTS  = ["com.privacy_tool.killswitch.plist", "com.privacy_tool.ntp_sync.plist"]
AGENT_PLISTS = ["com.privacy_tool.bridge_refresh.plist", "com.privacy_tool.log_purge.plist"]

if sys.platform == "win32":
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        _TTY = True
    except Exception:
        _TTY = sys.stdout.isatty()
else:
    _TTY = sys.stdout.isatty()

def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _TTY else text

def bold(t):    return _c("1",     t)
def dim(t):     return _c("2",     t)
def white(t):   return _c("97",    t)
def green(t):   return _c("92",    t)
def red(t):     return _c("91",    t)
def yellow(t):  return _c("93",    t)
def grey(t):    return _c("90",    t)

def cyan(t):    return white(t)
def blue(t):    return white(t)
def magenta(t): return white(t)

BANNER = r"""
  ██╗  ██╗██╗██████╗ ███████╗
  ██║  ██║██║██╔══██╗██╔════╝
  ███████║██║██║  ██║█████╗
  ██╔══██║██║██║  ██║██╔══╝
  ██║  ██║██║██████╔╝███████╗
  ╚═╝  ╚═╝╚═╝╚═════╝ ╚══════╝
"""

def print_banner(clear: bool = True) -> None:
    if clear:
        os.system("cls" if sys.platform == "win32" else "clear")
    print(bold(white(BANNER)))
    print(f"  {grey('made by plastral')}")
    print(f"  {grey('─' * 44)}")
    print()

class Spinner:

    _FRAMES = ["|", "/", "-", "\\", "|", "/", "-", "\\"]

    def __init__(self, label: str, sudo: bool = False):
        self._label   = label
        self._sudo    = sudo
        self._stop    = threading.Event()
        self._thread  = threading.Thread(target=self._spin, daemon=True)
        self._success: Optional[bool] = None
        self._note    = ""

    def __enter__(self):
        if _TTY and not self._sudo:
            self._thread.start()
        else:
            print(f"  ○ {self._label}...")
        return self

    def __exit__(self, exc_type, *_):
        self._success = exc_type is None
        self._stop.set()
        if _TTY and not self._sudo:
            self._thread.join()
            sys.stdout.write("\r\033[K")
            sys.stdout.flush()
        icon  = green("✓") if self._success else red("✗")
        note  = f"  {grey(self._note)}" if self._note else ""
        print(f"  {icon} {self._label}{note}")

    def note(self, text: str) -> None:
        self._note = text

    def _spin(self) -> None:
        i = 0
        while not self._stop.is_set():
            frame = white(self._FRAMES[i % len(self._FRAMES)])
            sys.stdout.write(f"\r  {frame} {self._label}  ")
            sys.stdout.flush()
            time.sleep(0.08)
            i += 1

def section(title: str) -> None:
    print()
    print(f"  {bold(cyan('▸'))} {bold(title)}")
    print(f"  {grey('─' * 44)}")

def info(msg: str) -> None:
    print(f"    {grey('·')} {msg}")

def warn(msg: str) -> None:
    print(f"    {yellow('!')} {yellow(msg)}")

def err(msg: str) -> None:
    print(f"    {red('✗')} {red(msg)}")

def ok(msg: str) -> None:
    print(f"    {green('✓')} {msg}")

def process_line(pid_or_name: str, description: str) -> None:
    print(f"    {cyan('⟳')} {bold(pid_or_name):<28} {grey(description)}")

class SystemInfo:
    def __init__(self):
        from platform_utils import IS_MACOS, IS_LINUX, IS_WINDOWS, os_name
        self.os_name     = os_name()
        self.is_macos    = IS_MACOS
        self.is_linux    = IS_LINUX
        self.is_windows  = IS_WINDOWS
        self.arch        = platform.machine()
        self.macos       = platform.mac_ver()[0] if IS_MACOS else ""
        self.macos_major = int(self.macos.split(".")[0]) if self.macos else 0
        self.python      = sys.version.split()[0]
        self.homebrew    = self._find_brew() if IS_MACOS else None
        self.brew_bin    = str(Path(self.homebrew).parent) if self.homebrew else ""
        self.python3     = self._find_python3()
        self.tor = (
            shutil.which("tor")
            or shutil.which("tor.exe")
            or self._brew_path("tor")
            or self._win_tor_path("tor.exe")
        )
        self.obfs4proxy = (
            shutil.which("obfs4proxy")
            or shutil.which("obfs4proxy.exe")
            or self._brew_path("obfs4proxy")
            or self._win_tor_path("obfs4proxy.exe")
            or self._win_tor_path("lyrebird.exe")
        )
        self.browsers    = self._detect_browsers()
        self.uid, self.gid = real_uid_gid()
        self.use_bootstrap = IS_MACOS and self.macos_major >= 13

    def _find_brew(self) -> Optional[str]:
        for candidate in [
            "/opt/homebrew/bin/brew",
            "/usr/local/bin/brew",
        ]:
            if os.path.isfile(candidate):
                return candidate
        return shutil.which("brew")

    def _brew_path(self, binary: str) -> Optional[str]:
        if not self.brew_bin:
            return None
        p = Path(self.brew_bin) / binary
        return str(p) if p.exists() else None

    def _win_tor_path(self, filename: str) -> Optional[str]:
        if not self.is_windows:
            return None
        base = Path(os.environ.get("LOCALAPPDATA", "")) / "HIDE" / "tor"
        if base.exists():
            found = next(base.rglob(filename), None)
            return str(found) if found else None
        return None

    def _find_python3(self) -> str:

        for candidate in [
            f"{Path(self.homebrew).parent}/python3" if self.homebrew else "",
            "/opt/homebrew/bin/python3",
            "/usr/local/bin/python3",
            sys.executable,
        ]:
            if candidate and os.path.isfile(candidate):
                return candidate
        return sys.executable

    def _detect_browsers(self) -> list[str]:
        found = []
        candidates: dict[str, list[str]] = {
            "Firefox": [
                "/Applications/Firefox.app",
                r"C:\Program Files\Mozilla Firefox\firefox.exe",
                r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
                "/usr/bin/firefox", "/snap/bin/firefox",
            ],
            "Chrome": [
                "/Applications/Google Chrome.app",
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                "/usr/bin/google-chrome", "/usr/bin/chromium-browser",
            ],
            "Brave": [
                "/Applications/Brave Browser.app",
                r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
                "/usr/bin/brave-browser",
            ],
            "Chromium": [
                "/Applications/Chromium.app",
                r"C:\Program Files\Chromium\Application\chrome.exe",
                "/usr/bin/chromium",
            ],
        }
        for name, paths in candidates.items():
            if any(Path(p).exists() for p in paths) or shutil.which(name.lower()):
                found.append(name)
        return found

    def print_summary(self) -> None:
        section("System Detection")
        info(f"OS            {bold(self.os_name)}  ({self.arch})")
        info(f"Python        {bold(self.python)}")
        if self.is_macos:
            info(f"Homebrew      {bold(self.homebrew or red('NOT FOUND'))}")
            info(f"launchctl     {bold('bootstrap mode' if self.use_bootstrap else 'load mode (legacy)')}")
        elif self.is_linux:
            from platform_utils import _linux_pkg_manager
            info(f"Package mgr   {bold(_linux_pkg_manager() or yellow('none detected'))}")
        elif self.is_windows:
            from platform_utils import _win_pkg_manager
            pkg = _win_pkg_manager() or yellow("winget/choco not found — will download directly")
            info(f"Package mgr   {bold(pkg)}")
        info(f"Tor           {bold(self.tor or yellow('not installed'))}")
        info(f"obfs4proxy    {bold(self.obfs4proxy or yellow('not installed'))}")
        info(f"Browsers      {bold(', '.join(self.browsers) or grey('none detected'))}")

SI = SystemInfo()

def _owner_spec(uid: int, gid: int) -> str:
    try:
        import grp
        import pwd
        user = pwd.getpwuid(uid).pw_name
        group = grp.getgrgid(gid).gr_name
        return f"{user}:{group}"
    except Exception:
        return str(uid)

def _run(cmd: list[str], uid: int = None, gid: int = None,
         capture: bool = True) -> subprocess.CompletedProcess:
    kwargs = dict(capture_output=capture, text=True)
    if uid is not None and gid is not None:
        def drop():
            os.setgid(gid)
            os.setuid(uid)
        kwargs["preexec_fn"] = drop
    return subprocess.run(cmd, **kwargs)

def _brew(args: list[str]) -> subprocess.CompletedProcess:
    brew_bin = SI.homebrew or "brew"
    return _run([brew_bin] + args, uid=SI.uid, gid=SI.gid)

def ensure_homebrew() -> bool:
    if SI.homebrew:
        return True
    with Spinner("Installing Homebrew"):
        result = subprocess.run(
            '/bin/bash -c "$(curl -fsSL '
            'https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"',
            shell=True, capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr[:200])
    SI.homebrew = SI._find_brew()
    SI.brew_bin = str(Path(SI.homebrew).parent) if SI.homebrew else ""
    return SI.homebrew is not None

def ensure_package(package: str, binary: str) -> str:
    from platform_utils import install_package
    existing = shutil.which(binary) or (SI._brew_path(binary) if SI.is_macos else None)
    if existing:
        with Spinner(f"{package} already installed") as s:
            s.note(existing)
        return existing
    pkg_label = "Homebrew" if SI.is_macos else ("apt/dnf/pacman" if SI.is_linux else "winget/direct download")
    with Spinner(f"Installing {package} via {pkg_label}"):
        path = install_package(package, binary)
    return path

def _launchctl_load(plist_path: Path, system: bool = True) -> None:
    label = plist_path.stem

    if system:

        r = subprocess.run(
            ["sudo", "launchctl", "bootstrap", "system", str(plist_path)],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            already = "already" in (r.stderr + r.stdout).lower()
            if already:
                return

            r2 = subprocess.run(
                ["sudo", "launchctl", "load", "-w", str(plist_path)],
                capture_output=True, text=True,
            )
            if r2.returncode != 0 and "already" not in (r2.stderr + r2.stdout).lower():
                raise RuntimeError(
                    f"launchctl bootstrap failed: {r.stderr.strip()}\n"
                    f"launchctl load fallback also failed: {r2.stderr.strip()}"
                )
    else:
        uid = str(SI.uid)

        subprocess.run(["chmod", "644", str(plist_path)], capture_output=True)

        r = subprocess.run(
            ["launchctl", "bootstrap", f"gui/{uid}", str(plist_path)],
            capture_output=True, text=True,
        )
        combined = (r.stderr + r.stdout).lower()
        if r.returncode != 0 and "already" not in combined:

            r2 = subprocess.run(
                ["launchctl", "load", "-w", str(plist_path)],
                capture_output=True, text=True,
            )
            combined2 = (r2.stderr + r2.stdout).lower()
            if r2.returncode != 0 and "already" not in combined2:

                label = plist_path.stem
                subprocess.run(
                    ["launchctl", "enable", f"gui/{uid}/{label}"],
                    capture_output=True,
                )
                r3 = subprocess.run(
                    ["launchctl", "kickstart", f"gui/{uid}/{label}"],
                    capture_output=True, text=True,
                )
                if r3.returncode != 0 and "already" not in (r3.stderr + r3.stdout).lower():

                    raise RuntimeError(
                        f"Agent load failed (bootstrap: {r.stderr.strip()}) "
                        f"(load: {r2.stderr.strip()})"
                    )

def _launchctl_unload(label: str, system: bool = True) -> None:
    if system:
        if SI.use_bootstrap:
            plist = DAEMON_DIR / f"{label}.plist"
            subprocess.run(
                ["sudo", "launchctl", "bootout", "system", str(plist)],
                capture_output=True,
            )
        else:
            subprocess.run(
                ["sudo", "launchctl", "unload", "-w",
                 str(DAEMON_DIR / f"{label}.plist")],
                capture_output=True,
            )
    else:
        uid = str(SI.uid)
        if SI.use_bootstrap:
            subprocess.run(
                ["launchctl", "bootout", f"gui/{uid}", label],
                capture_output=True,
            )
        else:
            subprocess.run(
                ["launchctl", "unload", "-w",
                 str(AGENT_DIR / f"{label}.plist")],
                capture_output=True,
            )

def _is_loaded(label: str) -> bool:
    r = subprocess.run(
        ["launchctl", "list", label],
        capture_output=True, text=True,
    )
    return r.returncode == 0

def _patch_plist_uid(src: Path, dst: Path) -> None:
    content = src.read_text(encoding="utf-8")

    content = re.sub(
        r"(<key>SUDO_UID</key>\s*<string>)\d+(</string>)",
        rf"\g<1>{SI.uid}\g<2>",
        content,
    )
    content = re.sub(
        r"(<key>SUDO_GID</key>\s*<string>)\d+(</string>)",
        rf"\g<1>{SI.gid}\g<2>",
        content,
    )

    if sys.platform == "win32":
        venv_python_path = TOOL_DIR / ".venv" / "Scripts" / "python.exe"
    else:
        venv_python_path = TOOL_DIR / ".venv" / "bin" / "python3"
    resolved_python = str(venv_python_path) if venv_python_path.exists() else SI.python3

    content = content.replace("HIDE_VENV_PYTHON", resolved_python)
    content = content.replace("HIDE_TOOL_DIR", str(TOOL_DIR))
    content = content.replace("HIDE_USER_HOME", str(USER_HOME))
    content = content.replace("HIDE_LOG_DIR", str(APP_SUPPORT))
    content = content.replace("HIDE_UID", str(SI.uid))
    content = content.replace("HIDE_GID", str(SI.gid))

    dst.write_text(content, encoding="utf-8")

PROCESS_DESCRIPTIONS = {
    "main.py":              "Orchestrator — boot sequence & watchdog",
    "killswitch.py":        "Kill-switch — pfctl network guard",
    "tor":                  "Tor daemon — encrypted onion routing",
    "obfs4proxy":           "obfs4 — Deep Packet Inspection bypass",
    "traffic_padding.py":   "Traffic padding — fingerprint disruption",
    "tor_control.py":       "Control monitor — circuit health & NEWNYM",
    "bridge_rotation.py":   "Bridge rotation — fresh MOAT bridges",
    "log_purge.py":         "Log purge — secure overwrite old logs",
    "ntp_over_tor.py":      "NTP sync — clock via Tor (no UDP/123 leak)",
}

def show_running_processes() -> None:
    section("Running HIDE Processes")
    found_any = False

    if SI.is_windows:
        result = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True, text=True,
        )
        for line in result.stdout.splitlines():
            parts = [p.strip('"') for p in line.split('","')]
            if len(parts) < 2:
                continue
            name = parts[0].lower()
            pid  = parts[1]
            for script, desc in PROCESS_DESCRIPTIONS.items():
                if script.lower().replace(".py", "") in name or script.lower() in name:
                    process_line(f"PID {pid} · {parts[0]}", desc)
                    found_any = True
                    break
    else:
        result = subprocess.run(["ps", "aux"], capture_output=True, text=True)
        seen_pids: set[str] = set()
        for line in result.stdout.splitlines():
            parts = line.split(None, 10)
            if len(parts) < 11:
                continue
            pid     = parts[1]
            cmd_col = parts[10]
            if pid in seen_pids:
                continue
            for script, desc in PROCESS_DESCRIPTIONS.items():
                match = False
                if script in ("tor", "obfs4proxy"):
                    exe   = cmd_col.split()[0] if cmd_col else ""
                    match = (exe.endswith(f"/{script}") or exe == script) and \
                            (str(APP_SUPPORT) in line or str(TOOL_DIR) in line or "privacy_tool" in line)
                else:
                    match = script in line and str(TOOL_DIR) in line
                if match:
                    process_line(f"PID {pid} · {script}", desc)
                    seen_pids.add(pid)
                    found_any = True
                    break

    if not found_any:
        info(grey("No HIDE processes currently running"))

def self_test() -> bool:
    section("Self-Test — Verifying Privacy Protection")
    all_passed = True

    if SI.is_windows:
        r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq tor.exe"], capture_output=True, text=True)
        tor_running = "tor.exe" in r.stdout.lower()
    else:
        r = subprocess.run(["pgrep", "-x", "tor"], capture_output=True, text=True)
        tor_running = r.returncode == 0
    if tor_running:
        ok("Tor process is running")
    else:
        err("Tor process NOT running")
        all_passed = False

    try:
        with socket.create_connection(("127.0.0.1", 9050), timeout=3):
            ok("SOCKS proxy reachable on 127.0.0.1:9050")
    except OSError:
        err("SOCKS proxy NOT reachable on port 9050")
        all_passed = False

    tor_log = APP_SUPPORT / "tor.log"
    pct = 0
    if tor_log.exists():
        for line in tor_log.read_text(errors="replace").splitlines():
            m = re.search(r"Bootstrapped\s+(\d+)%", line, re.I)
            if m:
                pct = max(pct, int(m.group(1)))
    if pct >= 100:
        ok(f"Tor bootstrap complete  {grey('(100%)')}")
    elif pct > 0:
        warn(f"Tor still bootstrapping  {grey(f'({pct}%)')}")
    else:
        warn("Tor bootstrap status unknown (log not yet written)")

    info("Checking exit IP via Tor SOCKS proxy...")
    r = subprocess.run(
        ["curl", "-s", "--max-time", "12",
         "--socks5-hostname", "127.0.0.1:9050",
         "https://check.torproject.org/api/ip"],
        capture_output=True, text=True,
    )
    if r.returncode == 0:
        try:
            data = json.loads(r.stdout)
            ip   = data.get("IP", "unknown")
            is_tor = data.get("IsTor", False)
            if is_tor:
                ok(f"Exit IP: {bold(ip)}  {green('✓ confirmed Tor exit node')}")
            else:
                warn(f"Exit IP: {bold(ip)}  {yellow('⚠ not flagged as Tor exit')}")
                all_passed = False
        except json.JSONDecodeError:
            warn("Could not parse Tor check response")
    else:
        warn("Could not reach check.torproject.org via Tor (still bootstrapping?)")

    if SI.is_macos:
        r = subprocess.run(
            ["pfctl", "-a", "com.privacy_tool.dns", "-sr"],
            capture_output=True, text=True,
        )
        if "block drop" in r.stdout.lower() or "rdr" in r.stdout.lower():
            ok("DNS redirect active  (pfctl anchor loaded)")
        else:
            warn("DNS anchor not detected — DNS may leak")
        if "inet6" in r.stdout.lower():
            ok("IPv6 blocked  (pfctl anchor)")
        else:
            warn("IPv6 block not detected")
        r2 = subprocess.run(
            ["pfctl", "-a", "com.privacy_tool.killswitch", "-sr"],
            capture_output=True, text=True,
        )
        if "pass" in r2.stdout.lower():
            ok("Kill-switch armed and in pass state  (Tor is up)")
        elif "block" in r2.stdout.lower():
            warn("Kill-switch in BLOCK state  (Tor may still be connecting)")
        else:
            warn("Kill-switch anchor not detected")
    elif SI.is_windows:
        r = subprocess.run(
            ["netsh", "advfirewall", "firewall", "show", "rule", "name=HIDE_block_out"],
            capture_output=True, text=True,
        )
        if "HIDE_block_out" in r.stdout:
            ok("Kill-switch firewall rules active")
        else:
            warn("Kill-switch firewall rules not detected")
    elif SI.is_linux:
        r = subprocess.run(["iptables", "-L", "OUTPUT", "-n"], capture_output=True, text=True)
        if "DROP" in r.stdout:
            ok("Kill-switch iptables rules active")
        else:
            warn("Kill-switch iptables rules not detected")

    try:
        from platform_utils import hosts_file
        hf = hosts_file()
        blocked = "privacy_tool telemetry block" in hf.read_text(errors="replace")
        if blocked:
            ok(f"Telemetry block active  ({hf})")
        else:
            warn("Telemetry hosts-file block not found")
    except OSError:
        pass

    manifest = APP_SUPPORT / "integrity_manifest.json"
    if manifest.exists():
        ok(f"Integrity manifest present  {grey(f'({len(json.loads(manifest.read_text()))} files)')}")
    else:
        warn("Integrity manifest missing — run install to create it")

    try:
        import sip_check
        sip_status = sip_check.get_sip_status()
        if sip_status == "enabled":
            ok(f"SIP  {grey('System Integrity Protection enabled')}")
        elif sip_status == "disabled":
            warn("SIP DISABLED — local attacker can bypass all protections")
            all_passed = False
        else:
            warn(f"SIP status unknown")
    except Exception:
        pass

    try:
        import swap_check
        fv = swap_check.filevault_enabled()
        if fv:
            ok("FileVault enabled  (swap encrypted)")
        else:
            warn("FileVault OFF — swap files unencrypted, enable in System Settings")
    except Exception:
        pass

    try:
        import timezone_utc
        tz = timezone_utc.get_current_timezone()
        if tz.upper() in ("UTC", "GMT", "ETC/UTC", "ETC/GMT"):
            ok(f"Timezone  {grey(tz)} — UTC active")
        else:
            warn(f"Timezone is {tz} — not UTC (run install to fix)")
    except Exception:
        pass

    print()
    if all_passed:
        print(f"  {green('━' * 44)}")
        print(f"  {bold(green('  ✓  All tests passed — you are hidden.'))}")
        print(f"  {green('━' * 44)}")
    else:
        print(f"  {yellow('━' * 44)}")
        print(f"  {bold(yellow('  ⚠  Some checks failed — see warnings above.'))}")
        print(f"  {yellow('━' * 44)}")
    print()
    return all_passed

def _silence_logging() -> tuple[list, list]:
    logging.disable(logging.CRITICAL)
    root = logging.getLogger()
    root_handlers = root.handlers[:]
    root.handlers = [logging.NullHandler()]

    silenced: list[tuple] = []
    for name, logger in list(logging.Logger.manager.loggerDict.items()):
        if isinstance(logger, logging.Logger) and logger.handlers:
            silenced.append((logger, logger.handlers[:], logger.propagate))
            logger.handlers = []
            logger.propagate = False
    return root_handlers, silenced

def _restore_logging(state: tuple) -> None:
    root_handlers, silenced = state
    logging.disable(logging.NOTSET)
    root = logging.getLogger()
    root.handlers = root_handlers
    for logger, handlers, propagate in silenced:
        logger.handlers = handlers
        logger.propagate = propagate

class RollbackManager:

    def __init__(self):
        self._actions: list[tuple[str, callable]] = []
        self._active  = False

    def register(self, label: str, fn: callable) -> None:
        self._actions.append((label, fn))

    def rollback(self) -> None:
        if not self._actions:
            return
        print()
        print(f"  {yellow('─' * 44)}")
        print(f"  {yellow('!')} Rolling back — restoring system to pre-install state...")
        print(f"  {yellow('─' * 44)}")
        print()

        self._restore_network_now()

        for label, fn in reversed(self._actions):
            try:
                with Spinner(f"Undoing: {label}"):
                    fn()
            except Exception:
                pass

        print()
        print(f"  {green('─' * 44)}")
        print(f"  {green('✓')} Rollback complete — your system is back to normal.")
        print(f"  {green('─' * 44)}")
        print()

    def _restore_network_now(self) -> None:
        try:
            from platform_utils import firewall_pass as _fw_pass
            _fw_pass()
        except Exception:
            pass
        if SI.is_macos:
            try:
                for anchor in ["com.privacy_tool.killswitch", "com.privacy_tool.dns",
                               "com.privacy_tool.telemetry", "com.privacy_tool.ntp"]:
                    subprocess.run(["sudo", "pfctl", "-a", anchor, "-F", "all"],
                                   capture_output=True, timeout=5)
                for iface in ["en0", "en1"]:
                    subprocess.run(["networksetup", "-setairportpower", iface, "on"],
                                   capture_output=True, timeout=5)
                    subprocess.run(["ifconfig", iface, "up"], capture_output=True, timeout=5)
            except Exception:
                pass
        elif SI.is_windows:
            try:
                for rule in ["HIDE_block_out", "HIDE_block_in", "HIDE_block_dns",
                             "HIDE_block_dns_udp", "HIDE_block_dns_tcp",
                             "HIDE_block_ntp", "HIDE_block_ipv6"]:
                    subprocess.run(["netsh", "advfirewall", "firewall", "delete", "rule",
                                    f"name={rule}"], capture_output=True, timeout=5)
            except Exception:
                pass

    def __enter__(self) -> "RollbackManager":
        self._active = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if exc_type is not None:
            self.rollback()
            return True
        return False

def _live_bootstrap_wait(timeout_s: int = 360, tor_proc=None) -> bool:
    log_path    = APP_SUPPORT / "tor.log"
    start_time  = time.monotonic()
    deadline    = start_time + timeout_s
    file_pos    = log_path.stat().st_size if log_path.exists() else 0
    last_pct    = 0
    last_drawn  = -1
    _boot_re    = re.compile(r"Bootstrapped\s+(\d+)%[^:]*:\s*(.*)", re.IGNORECASE)

    def _draw(pct: int, msg: str) -> None:
        elapsed  = int(time.monotonic() - start_time)
        bar_fill = int(pct / 5)
        bar      = white("█" * bar_fill) + grey("░" * (20 - bar_fill))
        pct_str  = bold(white(f"{pct:>3}%"))
        msg_str  = grey(msg[:40]) if msg else grey("Connecting...")
        line     = f"  {pct_str}  {bar}  {msg_str}  {grey(f'{elapsed}s')}"
        if _TTY:
            sys.stdout.write(f"\r\033[K{line}")
            sys.stdout.flush()
        else:
            print(line)

    print()
    print(f"  {bold(white('Connecting to Tor'))}  {grey(f'(timeout: {timeout_s}s)')}")
    print()
    _draw(0, "Starting up...")

    while time.monotonic() < deadline:
        if log_path.exists():
            try:
                with open(log_path, "r", errors="replace") as fh:
                    fh.seek(file_pos)
                    chunk = fh.read()
                    file_pos = fh.tell()
                for m in _boot_re.finditer(chunk):
                    pct = int(m.group(1))
                    msg = m.group(2).strip()
                    if pct != last_pct:
                        last_pct = pct
                        _draw(pct, msg)
            except OSError:
                pass

        if last_pct >= 100 or last_pct != last_drawn:
            try:
                with socket.create_connection(("127.0.0.1", 9050), timeout=2):
                    _draw(100, "Connected")
                    if _TTY:
                        sys.stdout.write("\n")
                    print()
                    return True
            except OSError:
                pass

        if last_pct == last_drawn and _TTY:
            elapsed = int(time.monotonic() - start_time)
            bar_fill = int(last_pct / 5)
            line = (
                f"\r\033[K  {bold(white(f'{last_pct:>3}%'))}  "
                f"{white('█' * bar_fill)}{grey('░' * (20 - bar_fill))}  "
                f"{grey('Connecting...')}  {grey(f'{elapsed}s')}"
            )
            sys.stdout.write(line)
            sys.stdout.flush()

        if tor_proc is not None and tor_proc.poll() is not None:
            if _TTY:
                sys.stdout.write("\n")
            print()
            err("Tor process exited unexpectedly.")
            for candidate in [log_path, APP_SUPPORT / "tor_startup.log"]:
                if candidate.exists() and candidate.stat().st_size > 0:
                    lines = candidate.read_text(errors="replace").splitlines()
                    last_lines = [l for l in lines[-20:] if l.strip()]
                    if last_lines:
                        print(f"  {grey('Tor output:')}")
                        for l in last_lines[-10:]:
                            print(f"    {grey(l)}")
                        break
            return False

        last_drawn = last_pct
        time.sleep(2)

    if _TTY:
        sys.stdout.write("\n")
    return False

def cmd_install() -> None:
    _log_state = _silence_logging()
    _rb        = RollbackManager()
    print_banner(clear=False)
    print(f"  {bold('Installing HIDE...')}")
    SI.print_summary()

    try:

        section("Privilege Check")
        if SI.is_windows:
            import ctypes
            if ctypes.windll.shell32.IsUserAnAdmin():
                ok("Running as Administrator")
            else:
                warn("Not running as Administrator — some steps may fail.")
        else:
            r = subprocess.run(["sudo", "-n", "true"], capture_output=True)
            if r.returncode != 0:
                warn("sudo access required. You may be prompted for your password during install.")
            else:
                ok("sudo access confirmed (no password prompt needed)")

        section("Dependencies")

        with Spinner("Creating HIDE virtual environment (.venv)"):
          from process_utils import ensure_venv_with_setproctitle
          venv_python = ensure_venv_with_setproctitle()
        info(f"venv Python → {grey(venv_python)}")
        info("setproctitle installed — process shows as 'HIDE Guard' in Activity Monitor")

        if SI.is_macos:
          try:
              ensure_homebrew()
              ok(f"Homebrew  {grey(SI.homebrew)}")
          except Exception as e:
              err(f"Homebrew install failed: {e}")
              sys.exit(1)

        try:
          tor_path = ensure_package("tor", "tor")
          SI.tor = tor_path
          info(f"tor → {grey(tor_path)}")
        except Exception as e:
          err(f"Tor install failed: {e}")
          sys.exit(1)

        try:
          obfs_path = ensure_package("obfs4proxy", "obfs4proxy")
          SI.obfs4proxy = obfs_path
          info(f"obfs4proxy → {grey(obfs_path)}")
        except Exception as e:
          err(f"obfs4proxy install failed: {e}")
          sys.exit(1)

        section("Directory Setup")
        with Spinner("Creating application support directory"):
            APP_SUPPORT.mkdir(parents=True, exist_ok=True)
            if SI.is_macos:
                AGENT_DIR.mkdir(parents=True, exist_ok=True)

            if not SI.is_windows:
                try:
                    subprocess.run(
                        ["sudo", "chown", "-R", _owner_spec(SI.uid, SI.gid), str(APP_SUPPORT)],
                        capture_output=True,
                    )
                except Exception:
                    pass

        _rb.register("Clear app support logs",
                     lambda: [f.unlink(missing_ok=True)
                              for f in APP_SUPPORT.glob("*.log")]
                              if APP_SUPPORT.exists() else None)
        ok(f"Log directory: {grey(str(APP_SUPPORT))}")

        section("Tor Configuration")
        with Spinner("Writing torrc with obfs4 bridges + circuit isolation"):
          sys.path.insert(0, str(TOOL_DIR))
          import tor_setup
          tor_setup.write_torrc()
        info(f"torrc → {grey(str(APP_SUPPORT / 'torrc'))}")
        info("Circuit isolation: IsolateClientAddr IsolateDestPort IsolateDestAddr")
        info("Control port: 9051 (CookieAuthentication)")
        info("Bridges: obfs4 stealth mode")

        with Spinner("Fetching fresh bridges from Tor MOAT API"):
          import bridge_rotation
          bridges = bridge_rotation.fetch_bridges_from_moat()
          if not bridges:
              bridges = bridge_rotation.FALLBACK_BRIDGES
          import tor_setup as _ts
          _orig = _ts.OBFS4_BRIDGES
          _ts.OBFS4_BRIDGES = bridges
          _ts.write_torrc()
          _ts.OBFS4_BRIDGES = _orig
        if bridges:
          ok(f"Active bridges: {len(bridges)}")
        else:
          warn("Using fallback hardcoded bridges")

        section("Security Baseline")
        with Spinner("Recording file integrity manifest"):
          import integrity_check
          integrity_check.update_manifest()
        ok("Integrity manifest written (tamper detection active)")

        section("Browser Hardening")
        if SI.browsers:
          with Spinner(f"Applying WebRTC + fingerprint policies to: {', '.join(SI.browsers)}"):
              import webrtc_prevention
              webrtc_prevention.apply_all()
          ok("WebRTC disabled, Tor proxy set, fingerprinting mitigated")
        else:
          warn("No supported browsers detected — skipping browser hardening")
          info("Install Firefox, Chrome, or Brave for browser privacy")

        section("System Service Installation")
        from platform_utils import install_service

        if sys.platform == "win32":
          venv_python = str(TOOL_DIR / ".venv" / "Scripts" / "python.exe")
        else:
          venv_python = str(TOOL_DIR / ".venv" / "bin" / "python3")
        if not Path(venv_python).exists():
          venv_python = SI.python3

        if SI.is_macos:
          info("Installing launchd daemons (kill-switch + NTP sync)")
          info("You may be prompted for your password...")
          print()
          for plist_name in ROOT_PLISTS:
              src   = LAUNCHD_DIR / plist_name
              dst   = DAEMON_DIR / plist_name
              label = plist_name.replace(".plist", "")
              with Spinner(f"Installing {label}", sudo=True):
                  _patch_plist_uid(src, src)
                  r = subprocess.run(["sudo", "cp", str(src), str(dst)], capture_output=True, text=True)
                  if r.returncode != 0:
                      raise RuntimeError(r.stderr)
                  subprocess.run(["sudo", "chown", "root:wheel", str(dst)], capture_output=True)
                  subprocess.run(["sudo", "chmod", "644", str(dst)], capture_output=True)
                  _launchctl_load(dst, system=True)
          for plist_name in AGENT_PLISTS:
              src   = LAUNCHD_DIR / plist_name
              dst   = AGENT_DIR / plist_name
              label = plist_name.replace(".plist", "")
              with Spinner(f"Installing {label}") as s:
                  try:
                      _patch_plist_uid(src, dst)
                      _launchctl_load(dst, system=False)
                  except RuntimeError:
                      s.note("scheduled — will activate on next login")

        elif SI.is_linux:
          info("Installing systemd services")
          linux_services = [
              ("hide-killswitch", "HIDE Network Kill-Switch", str(TOOL_DIR / "core" / "main.py")),
              ("hide-bridge-refresh", "HIDE Bridge Rotation", str(TOOL_DIR / "core" / "bridge_rotation.py")),
              ("hide-ntp-sync", "HIDE NTP Sync over Tor", str(TOOL_DIR / "privacy" / "ntp_over_tor.py")),
              ("hide-log-purge", "HIDE Secure Log Purge", str(TOOL_DIR / "system" / "log_purge.py")),
          ]
          for svc_name, svc_desc, svc_script in linux_services:
              with Spinner(f"Installing {svc_name}.service", sudo=True):
                  install_service(svc_name, svc_desc, venv_python, svc_script)
          ok("All systemd services installed and enabled")

        elif SI.is_windows:
          info("Registering Task Scheduler entries")
          windows_services = [
              ("hide-killswitch", "HIDE Network Kill-Switch", str(TOOL_DIR / "core" / "main.py")),
              ("hide-bridge-refresh", "HIDE Bridge Rotation", str(TOOL_DIR / "core" / "bridge_rotation.py")),
              ("hide-ntp-sync", "HIDE NTP Sync over Tor", str(TOOL_DIR / "privacy" / "ntp_over_tor.py")),
              ("hide-log-purge", "HIDE Secure Log Purge", str(TOOL_DIR / "system" / "log_purge.py")),
          ]
          for svc_name, svc_desc, svc_script in windows_services:
              with Spinner(f"Registering {svc_name} task"):
                  install_service(svc_name, svc_desc, venv_python, svc_script)
          ok("All Task Scheduler entries registered")

        section("Starting Tor")
        if SI.is_windows:
            subprocess.run(["taskkill", "/F", "/IM", "tor.exe"], capture_output=True)
            with Spinner("Adding Windows Defender exclusions for Tor"):
                tor_dir = str(Path(SI.tor).parent) if SI.tor else ""
                if tor_dir:
                    subprocess.run(
                        ["powershell", "-Command",
                         f"Add-MpPreference -ExclusionPath '{tor_dir}' 2>$null"],
                        capture_output=True, timeout=15,
                    )
                    subprocess.run(
                        ["powershell", "-Command",
                         f"Add-MpPreference -ExclusionPath '{str(APP_SUPPORT)}' 2>$null"],
                        capture_output=True, timeout=15,
                    )
        else:
            subprocess.run(["pkill", "-x", "tor"], capture_output=True)
        time.sleep(2)

        torrc    = APP_SUPPORT / "torrc"
        tor_bin  = SI.tor or "tor"

        if SI.is_windows:
            with Spinner("Checking tor.exe is executable"):
                ver_check = subprocess.run(
                    [tor_bin, "--version"],
                    capture_output=True, text=True, timeout=10,
                    cwd=str(Path(tor_bin).parent),
                )
                if ver_check.returncode != 0 or not ver_check.stdout.strip():
                    raise RuntimeError(
                        f"tor.exe failed sanity check (rc={ver_check.returncode}).\n"
                        f"stdout: {ver_check.stdout[:300]}\n"
                        f"stderr: {ver_check.stderr[:300]}\n"
                        f"This usually means Windows Defender blocked it.\n"
                        f"Open Windows Security → Virus & threat protection → "
                        f"Exclusions → Add exclusion → Folder → {Path(tor_bin).parent}"
                    )
        else:
            with Spinner("Verifying Tor configuration"):
                verify = subprocess.run(
                    [tor_bin, "--verify-config", "-f", str(torrc)],
                    capture_output=True, text=True, timeout=15,
                )
                if verify.returncode != 0:
                    output = (verify.stdout + verify.stderr).strip()
                    if not output and torrc.exists():
                        output = "torrc:\n" + torrc.read_text(errors="replace")
                    raise RuntimeError(f"Tor config error:\n{output[-1200:]}")

        info("Launching Tor with obfs4 bridges...")

        startup_log = APP_SUPPORT / "tor_startup.log"
        popen_kwargs: dict = {
            "stdout": open(startup_log, "w"),
            "stderr": subprocess.STDOUT,
        }
        if SI.is_windows:
            popen_kwargs["cwd"] = str(Path(tor_bin).parent)
        else:
            def _drop():
                os.setgid(SI.gid)
                os.setuid(SI.uid)
            popen_kwargs["preexec_fn"] = _drop

        tor_proc = subprocess.Popen([tor_bin, "-f", str(torrc)], **popen_kwargs)
        time.sleep(5)
        if tor_proc.poll() is not None:
            output_lines = []
            for candidate in [startup_log, APP_SUPPORT / "tor.log"]:
                if candidate.exists() and candidate.stat().st_size > 0:
                    output_lines.append(f"[{candidate.name}]\n{candidate.read_text(errors='replace').strip()}")
            if not output_lines and torrc.exists():
                output_lines.append(f"[torrc]\n{torrc.read_text(errors='replace')}")
            if not output_lines:
                output_lines.append(
                    "No output captured. Tor may be blocked by Windows Defender.\n"
                    f"Try: Open Windows Security → Virus & threat protection → "
                    f"Exclusions → Add → Folder → {Path(tor_bin).parent}"
                )
            raise RuntimeError(f"Tor exited immediately:\n" + "\n".join(output_lines)[-1500:])
        if SI.is_windows:
            _rb.register("Kill Tor process",
                         lambda: subprocess.run(["taskkill", "/F", "/IM", "tor.exe"], capture_output=True))
        else:
            _rb.register("Kill Tor process",
                         lambda: subprocess.run(["pkill", "-x", "tor"], capture_output=True))
        process_line(f"PID {tor_proc.pid}", "tor — encrypted onion routing")

        ok_boot = _live_bootstrap_wait(timeout_s=360, tor_proc=tor_proc)
        if not ok_boot:
            raise RuntimeError(
                "Tor could not connect within 6 minutes.\n"
                "    This usually means the bridges are blocked on your network.\n"
                "    Try Reinstall to fetch fresh bridges, or check your internet connection."
            )
        ok("Tor connected successfully")

        section("Activating Privacy Layers")

        with Spinner("DNS leak prevention"):
            import dns_leak_prevention
            dns_leak_prevention.activate()
        _rb.register("Restore DNS resolver settings", dns_leak_prevention.deactivate)
        process_line("dns", "DNS redirected through Tor")

        with Spinner("Blocking telemetry domains (/etc/hosts)"):
            import telemetry_block
            telemetry_block.activate()
        _rb.register("Remove telemetry /etc/hosts block", telemetry_block.remove_hosts_block)
        ok("Apple + browser telemetry endpoints blocked")

        with Spinner("Randomizing MAC address") as s:

            _mac_script = str(TOOL_DIR / "privacy" / "mac_randomize.py")
            _mac_cmd = [sys.executable, _mac_script] if SI.is_windows else ["sudo", sys.executable, _mac_script]
            _r = subprocess.run(
                _mac_cmd,
                capture_output=True, text=True,
            )
            _out = (_r.stdout + _r.stderr).lower()
            if "randomized" in _out or _r.returncode == 0:

                import re as _re
                _m = _re.search(r"(\d+) randomized.*?(\d+) skipped", _r.stdout)
                if _m:
                    ok_count, skipped = int(_m.group(1)), int(_m.group(2))
                    if ok_count == 0:
                        s.note(f"no active interfaces ({skipped} skipped)")
                    elif skipped > 0:
                        s.note(f"{ok_count} randomized, {skipped} skipped")
            else:
                s.note("skipped (sudo not available or no active interfaces)")

        with Spinner("Randomizing hostname") as s:
            _hn_script = str(TOOL_DIR / "privacy" / "hostname_randomize.py")
            _hn_cmd = [sys.executable, _hn_script] if SI.is_windows else ["sudo", sys.executable, _hn_script]
            _rh = subprocess.run(
                _hn_cmd,
                capture_output=True, text=True,
            )
            if _rh.returncode == 0:
                import re as _re2
                _m2 = _re2.search(r"→\s+(\S+)", _rh.stdout + _rh.stderr)
                if _m2:
                    s.note(_m2.group(1))
            else:
                s.note("skipped (sudo unavailable)")

        with Spinner("Forcing timezone to UTC"):
            import timezone_utc
            timezone_utc.activate()
        _rb.register("Restore original timezone", timezone_utc.deactivate)
        ok("System timezone set to UTC — timezone fingerprinting blocked")

        with Spinner("Syncing clock via Tor (disabling system NTP)"):
            import ntp_over_tor
            ntp_over_tor.activate()
        if SI.is_macos:
            _rb.register("Re-enable Apple NTP",
                         lambda: subprocess.run(["sudo","launchctl","load","-w",
                             "/System/Library/LaunchDaemons/com.apple.timed.plist"], capture_output=True))
        ok("Clock synced via HTTP-over-Tor, system NTP blocked")

        with Spinner("Starting traffic padding thread"):
            import traffic_padding
            traffic_padding.start()
        process_line("thread:traffic-padding", "dummy HEAD requests — timing fingerprint disruption")

        with Spinner("Starting Tor control port monitor"):
            import tor_control
            tor_control.run_monitor()
        process_line("thread:tor-control-monitor", "circuit events, NEWNYM capability")

        with Spinner("Starting circuit renewal (rotates every 10 min)"):
            import circuit_renewal
            circuit_renewal.start()
        process_line("thread:circuit-renewal", "NEWNYM every 10 min — prevents traffic correlation")

        if SI.is_macos:
            with Spinner("Checking FileVault / swap encryption"):
                import swap_check
                result = swap_check.check()
            if result["filevault"]:
                ok(f"FileVault enabled — swap encrypted")
            else:
                warn("FileVault is OFF — enable it in System Settings → Privacy & Security → FileVault")

            with Spinner("Checking System Integrity Protection (SIP)"):
                import sip_check
                sip_ok = sip_check.check()
            if sip_ok:
                ok("SIP enabled — system files protected against local tampering")
            else:
                warn("SIP is DISABLED — reboot to Recovery Mode and run: csrutil enable")

        _restore_logging(_log_state)
        self_test()

        section("Installation Complete")
        print(f"  {bold(green('HIDE is active and protecting your network.'))}")
        print()
        _hide_cmd = "python hide.py" if SI.is_windows else "sudo python3 hide.py"
        print(f"  {bold('Quick commands:')}")
        print(f"    {cyan(_hide_cmd)}   — open this menu (Install / Status / Private Browser)")
        print(f"    {grey('Menu option [4]')}       — live status + self-test")
        print(f"    {grey('Menu option [5]')}       — launch a hardened browser routed through Tor")
        print()
        show_running_processes()
        print()

    except Exception as exc:
        _restore_logging(_log_state)
        print()
        print(f"  {red('─' * 44)}")
        print(f"  {red('✗')} {bold(red('Install failed:'))} {str(exc).splitlines()[0]}")
        print(f"  {red('─' * 44)}")
        _rb.rollback()
        input(f"\n  {grey('Press Enter to return to menu...')}")

def cmd_remove() -> None:
    _silence_logging()
    print_banner()
    print(f"  {bold(red('Removing HIDE...'))} {grey('(all components will be unloaded and deleted)')}")
    print()

    from platform_utils import (
        IS_MACOS, IS_LINUX, IS_WINDOWS,
        firewall_pass, remove_hosts_block, remove_service,
    )

    section("Stopping Services")

    if IS_MACOS:
        for label in [p.replace(".plist", "") for p in ROOT_PLISTS]:
            with Spinner(f"Unloading {label}"):
                _launchctl_unload(label, system=True)
                plist = DAEMON_DIR / f"{label}.plist"
                if plist.exists():
                    subprocess.run(["sudo", "rm", str(plist)], capture_output=True)
        for label in [p.replace(".plist", "") for p in AGENT_PLISTS]:
            with Spinner(f"Unloading {label}"):
                _launchctl_unload(label, system=False)
                plist = AGENT_DIR / f"{label}.plist"
                if plist.exists():
                    plist.unlink(missing_ok=True)
    elif IS_LINUX:
        with Spinner("Removing systemd service", sudo=True):
            remove_service("hide-killswitch")
    elif IS_WINDOWS:
        with Spinner("Removing Task Scheduler entry"):
            remove_service("hide-killswitch")

    section("Stopping Tor")
    with Spinner("Killing Tor process"):
        if IS_WINDOWS:
            subprocess.run(["taskkill", "/F", "/IM", "tor.exe"], capture_output=True)
        else:
            subprocess.run(["pkill", "-x", "tor"], capture_output=True)
        time.sleep(1)

    section("Removing Privacy Layers")

    with Spinner("Flushing firewall rules"):
        try:
            firewall_pass()
        except Exception:
            pass
        if IS_MACOS:
            for anchor in ["com.privacy_tool.killswitch","com.privacy_tool.dns",
                           "com.privacy_tool.telemetry","com.privacy_tool.ntp"]:
                subprocess.run(["sudo","pfctl","-a",anchor,"-F","all"], capture_output=True)
        elif IS_LINUX:
            for cmd in [
                ["sudo","iptables","-F"],
                ["sudo","iptables","-t","nat","-F"],
                ["sudo","ip6tables","-F"],
            ]:
                subprocess.run(cmd, capture_output=True)

    with Spinner("Removing telemetry /etc/hosts block"):
        try:
            remove_hosts_block()
        except Exception:
            pass

    with Spinner("Removing DNS resolver override"):
        try:
            import dns_leak_prevention
            dns_leak_prevention.deactivate()
        except Exception:
            resolver = Path("/etc/resolver/privacy_tool_dns")
            if resolver.exists():
                subprocess.run(["sudo", "rm", str(resolver)], capture_output=True)

    if SI.is_macos:
        with Spinner("Re-enabling system NTP"):
            subprocess.run(
                ["sudo", "launchctl", "load", "-w",
                 "/System/Library/LaunchDaemons/com.apple.timed.plist"],
                capture_output=True,
            )
    elif SI.is_linux:
        with Spinner("Re-enabling system NTP"):
            subprocess.run(["sudo", "timedatectl", "set-ntp", "true"], capture_output=True)
    elif SI.is_windows:
        with Spinner("Re-enabling system NTP"):
            subprocess.run(["sc", "config", "w32tm", "start=auto"], capture_output=True)
            subprocess.run(["sc", "start", "w32tm"], capture_output=True)

    with Spinner("Restoring original timezone"):
        try:
            import timezone_utc
            timezone_utc.deactivate()
        except Exception:
            pass

    section("Secure Removal of Application Files")

    with Spinner("Securely wiping log files"):
        import secrets as _secrets
        _passes = 3
        if APP_SUPPORT.exists():
            for _f in APP_SUPPORT.rglob("*.log"):
                try:
                    _size = _f.stat().st_size
                    if _size > 0:
                        with open(_f, "r+b") as _fh:
                            for _ in range(_passes):
                                _fh.seek(0)
                                _fh.write(_secrets.token_bytes(_size))
                                _fh.flush()
                        _f.unlink()
                except OSError:
                    pass

    with Spinner("Removing application support directory"):
        import shutil as _shutil
        if APP_SUPPORT.exists():
            _shutil.rmtree(str(APP_SUPPORT), ignore_errors=True)

    with Spinner("Removing browser policies"):
        policy_dirs = []
        if SI.is_macos:
            policy_dirs = [
                USER_HOME / "Library/Application Support/Google/Chrome/policies/managed",
                USER_HOME / "Library/Application Support/Chromium/policies/managed",
                USER_HOME / "Library/Application Support/BraveSoftware/Brave-Browser/policies/managed",
            ]
        elif SI.is_linux:
            policy_dirs = [
                USER_HOME / ".config/google-chrome/policies/managed",
                USER_HOME / ".config/chromium/policies/managed",
                USER_HOME / ".config/BraveSoftware/Brave-Browser/policies/managed",
            ]
        elif SI.is_windows:
            local = Path(os.environ.get("LOCALAPPDATA", USER_HOME))
            policy_dirs = [
                local / "Google/Chrome/User Data/policies/managed",
                local / "Chromium/User Data/policies/managed",
                local / "BraveSoftware/Brave-Browser/User Data/policies/managed",
            ]
        for policy_dir in policy_dirs:
            p = policy_dir / "privacy_tool.json"
            p.unlink(missing_ok=True)
        if SI.is_windows:
            try:
                import webrtc_prevention
                webrtc_prevention.remove_chromium_windows_registry()
            except Exception:
                pass

    with Spinner("Removing Firefox user.js from profiles"):
        firefox_roots = []
        if SI.is_macos:
            firefox_roots = [USER_HOME / "Library/Application Support/Firefox/Profiles"]
        elif SI.is_linux:
            firefox_roots = [USER_HOME / ".mozilla/firefox"]
        elif SI.is_windows:
            appdata = Path(os.environ.get("APPDATA", USER_HOME))
            firefox_roots = [appdata / "Mozilla/Firefox/Profiles"]
        for profile_root in firefox_roots:
            if profile_root.exists():
                for d in profile_root.iterdir():
                    uj = d / "user.js"
                    uj.unlink(missing_ok=True)

    print()
    print(f"  {bold(green('HIDE has been fully removed.'))}  {grey('Your system is back to defaults.')}")
    print()

def cmd_reinstall() -> None:
    print_banner(clear=False)
    print(f"  {bold(yellow('Reinstalling HIDE...'))} {grey('(remove → clean install)')}")
    time.sleep(1)
    cmd_remove()
    time.sleep(2)
    cmd_install()

def cmd_status() -> None:
    print_banner()
    show_running_processes()
    self_test()

def _print_plan(title: str, steps: list[str]) -> None:
    print_banner(clear=False)
    section(title)
    for step in steps:
        info(step)
    print()
    ok("Dry run complete. No changes were made.")

def cmd_dry_run(target: str = "install") -> None:
    target = target.lower().strip()
    common = [
        f"Detected OS: {SI.os_name} ({SI.arch})",
        f"App support directory: {APP_SUPPORT}",
        f"User home: {USER_HOME}",
    ]
    plans: dict[str, list[str]] = {
        "install": common + [
            "Check administrator/root privileges.",
            "Create or reuse the Python virtual environment.",
            "Install or locate Tor and obfs4proxy.",
            "Create the app support directory and service directories.",
            "Write torrc with SOCKS ports, control port, DNS resolver, and bridge settings.",
            "Fetch fresh obfs4 bridges, falling back to bundled bridges if needed.",
            "Record the file integrity manifest.",
            "Apply browser WebRTC/fingerprinting policies where supported.",
            "Install background services for the guard, bridge refresh, NTP sync, and log purge.",
            "Start Tor and wait for bootstrap.",
            "Activate DNS leak prevention, telemetry blocking, MAC/hostname randomization, "
            "NTP-over-Tor, timezone UTC, traffic padding, and circuit renewal.",
            "Run status/self-test at the end.",
        ],
        "remove": common + [
            "Unload HIDE services or scheduled tasks.",
            "Stop Tor.",
            "Flush HIDE firewall rules and DNS redirects.",
            "Remove HIDE hosts-file telemetry block.",
            "Restore DNS resolver settings.",
            "Re-enable system NTP.",
            "Restore the original timezone if a backup exists.",
            "Securely wipe HIDE log files and remove the app support directory.",
            "Remove browser policies and Firefox user.js files written by HIDE.",
        ],
        "rescue": common + [
            "Stop HIDE background services where possible.",
            "Stop Tor.",
            "Open the firewall and remove HIDE kill-switch rules.",
            "Restore DNS settings and clear HIDE DNS firewall rules.",
            "Remove HIDE telemetry entries from the hosts file.",
            "Re-enable system NTP.",
            "Restore the original timezone if a backup exists.",
            "Leave installed files in place so you can inspect or remove them later.",
        ],
        "status": common + [
            "List running HIDE-related processes.",
            "Check Tor process and SOCKS reachability.",
            "Read Tor bootstrap status from the log.",
            "Check firewall/DNS/hosts/integrity/timezone indicators where available.",
        ],
        "capabilities": common + [
            "Report package manager availability.",
            "Report service/firewall/DNS/browser support for this OS.",
            "Flag best-effort protections before install.",
            "Make no changes.",
        ],
    }
    if target not in plans:
        raise ValueError(f"Unknown dry-run target: {target}")
    _print_plan(f"Dry Run: {target}", plans[target])

def _capability_rows() -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []

    def add(name: str, status: str, note: str) -> None:
        rows.append((name, status, note))

    add("Platform", "ok", SI.os_name)
    add("Python", "ok", SI.python)
    add("Tor", "ok" if SI.tor else "missing", SI.tor or "will try to install")
    add("obfs4proxy", "ok" if SI.obfs4proxy else "missing", SI.obfs4proxy or "will try to install")

    if SI.is_macos:
        add("Package manager", "ok" if SI.homebrew else "missing", SI.homebrew or "Homebrew will be installed")
        add("Services", "ok", "launchd daemons and user agents")
        add("Firewall", "ok", "pf anchors")
        add("DNS protection", "ok", "pf redirect plus resolver override")
        add("Browser policies", "ok", "Firefox user.js and Chromium policy JSON")
        add("MAC randomization", "best-effort", "depends on interface and driver")
        add("Hostname randomization", "ok", "scutil ComputerName/HostName/LocalHostName")
        add("Disk/swap checks", "ok", "FileVault and SIP checks available")
    elif SI.is_linux:
        from platform_utils import _linux_pkg_manager
        pkg = _linux_pkg_manager()
        add("Package manager", "ok" if pkg else "missing", pkg or "manual package install may be needed")
        add("Services", "ok", "systemd services")
        add("Firewall", "ok", "iptables/ip6tables rules")
        add("DNS protection", "best-effort", "iptables redirect plus resolv.conf/systemd-resolved changes")
        add("Browser policies", "ok", "Firefox user.js and Chromium policy JSON")
        add("MAC randomization", "best-effort", "requires iproute2 and driver support")
        add("Hostname randomization", "ok", "hostnamectl")
        add("Disk/swap checks", "skipped", "macOS-only checks")
    elif SI.is_windows:
        from platform_utils import _win_pkg_manager
        pkg = _win_pkg_manager()
        add("Package manager", "ok" if pkg else "fallback", pkg or "Tor expert bundle direct download")
        add("Services", "ok", "Task Scheduler entries")
        add("Firewall", "ok", "Windows Defender Firewall rules")
        add("DNS protection", "best-effort", "adapter DNS set to local Tor resolver, restored on remove/rescue")
        add("Browser policies", "ok", "Firefox user.js and Chromium registry policy")
        add("MAC randomization", "best-effort", "many drivers ignore NetworkAddress")
        add("Hostname randomization", "reboot", "Rename-Computer may need restart")
        add("Disk/swap checks", "skipped", "macOS-only checks")
    else:
        add("Platform support", "unsupported", "macOS, Linux, and Windows are supported")

    add(
        "Detected browsers",
        "ok" if SI.browsers else "missing",
        ", ".join(SI.browsers) or "install Firefox, Chrome, Chromium, or Brave",
    )
    return rows

def cmd_capabilities() -> None:
    print_banner(clear=False)
    section("Capability Report")
    for name, status, note in _capability_rows():
        if status == "ok":
            label = green("ok")
        elif status in {"best-effort", "fallback", "reboot", "missing", "skipped"}:
            label = yellow(status)
        else:
            label = red(status)
        print(f"    {bold(name):<24} {label:<20} {grey(note)}")
    print()
    info("This report does not change system settings.")

def cmd_help() -> None:
    print("""HIDE

Usage:
  python hide.py                       open the menu
  python hide.py --auto-install        run install without opening the menu
  python hide.py --rescue              emergency network restore
  python hide.py --capabilities        show supported protections on this machine
  python hide.py --dry-run install     show install plan without changing anything
  python hide.py --dry-run remove      show remove plan without changing anything
  python hide.py --dry-run rescue      show rescue plan without changing anything
  python hide.py --dry-run status      show status plan without changing anything
  python hide.py --dry-run capabilities show capability plan without changing anything

Use python3 instead of python on macOS/Linux if that is how Python is installed.
""")

def _stop_hide_services_for_rescue() -> None:
    from platform_utils import IS_MACOS, IS_LINUX, IS_WINDOWS
    if IS_MACOS:
        for label in [p.replace(".plist", "") for p in ROOT_PLISTS]:
            _launchctl_unload(label, system=True)
        for label in [p.replace(".plist", "") for p in AGENT_PLISTS]:
            _launchctl_unload(label, system=False)
    elif IS_LINUX:
        for name in ["hide-killswitch", "hide-bridge-refresh", "hide-ntp-sync", "hide-log-purge"]:
            subprocess.run(["sudo", "systemctl", "stop", name], capture_output=True)
    elif IS_WINDOWS:
        for name in ["hide-killswitch", "hide-bridge-refresh", "hide-ntp-sync", "hide-log-purge"]:
            subprocess.run(["schtasks", "/End", "/TN", f"HIDE\\{name}"], capture_output=True)

def _stop_tor_for_rescue() -> None:
    if SI.is_windows:
        subprocess.run(["taskkill", "/F", "/IM", "tor.exe"], capture_output=True)
    else:
        subprocess.run(["pkill", "-x", "tor"], capture_output=True)

def _reenable_ntp_for_rescue() -> None:
    if SI.is_macos:
        subprocess.run(
            ["sudo", "launchctl", "load", "-w",
             "/System/Library/LaunchDaemons/com.apple.timed.plist"],
            capture_output=True,
        )
    elif SI.is_linux:
        subprocess.run(["sudo", "timedatectl", "set-ntp", "true"], capture_output=True)
        for svc in ["systemd-timesyncd", "ntp", "chrony"]:
            subprocess.run(["sudo", "systemctl", "start", svc], capture_output=True)
    elif SI.is_windows:
        subprocess.run(["sc", "config", "w32tm", "start=auto"], capture_output=True)
        subprocess.run(["sc", "start", "w32tm"], capture_output=True)

def cmd_rescue() -> None:
    print_banner(clear=False)
    print(f"  {bold(yellow('Emergency restore'))} {grey('(network basics only)')}")
    print()
    warn("This does not uninstall HIDE. It only tries to get normal networking back.")

    section("Restoring Network")
    with Spinner("Stopping HIDE background services"):
        _stop_hide_services_for_rescue()

    with Spinner("Stopping Tor"):
        _stop_tor_for_rescue()

    with Spinner("Opening firewall and removing kill-switch rules"):
        try:
            from platform_utils import firewall_pass
            firewall_pass()
        except Exception:
            pass
        if SI.is_macos:
            for anchor in ["com.privacy_tool.killswitch", "com.privacy_tool.dns",
                           "com.privacy_tool.telemetry", "com.privacy_tool.ntp"]:
                subprocess.run(["sudo", "pfctl", "-a", anchor, "-F", "all"], capture_output=True)
        elif SI.is_linux:
            for cmd in [
                ["sudo", "iptables", "-D", "OUTPUT", "!", "-o", "lo", "-j", "DROP"],
                ["sudo", "iptables", "-D", "INPUT", "!", "-i", "lo", "-j", "DROP"],
                ["sudo", "ip6tables", "-D", "OUTPUT", "-j", "DROP"],
                ["sudo", "ip6tables", "-D", "INPUT", "-j", "DROP"],
            ]:
                subprocess.run(cmd, capture_output=True)
        elif SI.is_windows:
            for rule in ["HIDE_block_out", "HIDE_block_in", "HIDE_block_ipv6"]:
                subprocess.run(
                    ["netsh", "advfirewall", "firewall", "delete", "rule", f"name={rule}"],
                    capture_output=True,
                )

    with Spinner("Restoring DNS settings"):
        try:
            import dns_leak_prevention
            dns_leak_prevention.deactivate()
        except Exception:
            try:
                from platform_utils import firewall_restore_dns
                firewall_restore_dns()
            except Exception:
                pass

    with Spinner("Removing HIDE hosts-file block"):
        try:
            from platform_utils import remove_hosts_block
            remove_hosts_block()
        except Exception:
            pass

    with Spinner("Re-enabling system NTP"):
        _reenable_ntp_for_rescue()

    with Spinner("Restoring timezone backup"):
        try:
            import timezone_utc
            timezone_utc.deactivate()
        except Exception:
            pass

    print()
    ok("Emergency restore finished.")
    info("If networking is still broken, reboot once, then run Remove from the HIDE menu.")

_PRIVATE_PROFILE_ROOT = APP_SUPPORT / "private_browser_profiles"

_BROWSER_BINS: dict[str, list[str]] = {
    "Firefox": [
        "/Applications/Firefox.app/Contents/MacOS/firefox",
        r"C:\Program Files\Mozilla Firefox\firefox.exe",
        r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
        "/usr/bin/firefox", "/snap/bin/firefox",
        shutil.which("firefox") or "",
    ],
    "Chrome": [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        "/usr/bin/google-chrome", "/usr/bin/chromium-browser",
        shutil.which("google-chrome") or "",
    ],
    "Brave": [
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        "/usr/bin/brave-browser",
        shutil.which("brave-browser") or shutil.which("brave") or "",
    ],
    "Chromium": [
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        r"C:\Program Files\Chromium\Application\chrome.exe",
        "/usr/bin/chromium",
        shutil.which("chromium") or "",
    ],
}

_FIREFOX_USER_JS = """
user_pref("network.proxy.type", 1);
user_pref("network.proxy.socks", "127.0.0.1");
user_pref("network.proxy.socks_port", 9050);
user_pref("network.proxy.socks_version", 5);
user_pref("network.proxy.socks_remote_dns", true);
user_pref("network.proxy.no_proxies_on", "");
user_pref("media.peerconnection.enabled", false);
user_pref("media.peerconnection.ice.no_host", true);
user_pref("media.peerconnection.ice.proxy_only", true);
user_pref("privacy.resistFingerprinting", true);
user_pref("privacy.resistFingerprinting.letterboxing", true);
user_pref("webgl.disabled", true);
user_pref("geo.enabled", false);
user_pref("dom.battery.enabled", false);
user_pref("toolkit.telemetry.enabled", false);
user_pref("datareporting.healthreport.uploadEnabled", false);
user_pref("browser.safebrowsing.malware.enabled", false);
user_pref("browser.safebrowsing.phishing.enabled", false);
user_pref("network.prefetch-next", false);
user_pref("network.dns.disablePrefetch", true);
user_pref("privacy.firstparty.isolate", true);
user_pref("network.trr.mode", 5);
user_pref("general.useragent.override", "Mozilla/5.0 (Windows NT 10.0; rv:109.0) Gecko/20100101 Firefox/115.0");
user_pref("intl.accept_languages", "en-US, en");
""".strip()

_CHROMIUM_FLAGS = [
    "--proxy-server=socks5://127.0.0.1:9050",
    "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1",
    "--disable-webgl",
    "--disable-reading-from-canvas",
    "--no-pings",
    "--disable-background-networking",
    "--disable-sync",
    "--disable-translate",
    "--disable-default-apps",
    "--disable-component-update",
    "--metrics-recording-only",
    "--disable-breakpad",
    "--no-first-run",
    "--no-service-autorun",
    "--enforce-webrtc-ip-permission-check",
    "--webrtc-ip-handling-policy=disable_non_proxied_udp",
    "--disable-features=DnsOverHttps",
]

def _socks_up() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 9050), timeout=2):
            return True
    except OSError:
        return False

def _launch_firefox_private() -> None:
    binary = next(
        (b for b in _BROWSER_BINS["Firefox"] if b and os.path.isfile(b)), None
    )
    if not binary:
        raise FileNotFoundError("Firefox not found.")

    profile_dir = _PRIVATE_PROFILE_ROOT / "firefox"
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "user.js").write_text(_FIREFOX_USER_JS + "\n", encoding="utf-8")

    subprocess.Popen([
        binary,
        "--profile", str(profile_dir),
        "--no-remote",
        "--new-instance",
        "--class", "HIDE-Private",
    ])
    ok(f"Firefox private window launched  {grey(f'(profile: {profile_dir.name})')}")

def _launch_chromium_private(browser: str) -> None:
    binary = next(
        (b for b in _BROWSER_BINS[browser] if b and os.path.isfile(b)), None
    )
    if not binary:
        raise FileNotFoundError(f"{browser} not found.")

    profile_dir = _PRIVATE_PROFILE_ROOT / browser.lower().replace(" ", "_")
    profile_dir.mkdir(parents=True, exist_ok=True)

    subprocess.Popen(
        [binary, f"--user-data-dir={profile_dir}"]
        + _CHROMIUM_FLAGS
        + ["--window-workspace=HIDE Private"]
    )
    ok(f"{browser} private window launched  {grey(f'(isolated profile)')}")

def cmd_private_browser() -> None:
    print_banner()
    section("Launch Private Browser")

    if not _socks_up():
        err("Tor SOCKS proxy is not reachable on 127.0.0.1:9050")
        warn("Run Install first to start Tor before launching a private browser.")
        input(f"\n  {grey('Press Enter to return to menu...')}")
        return

    ok(f"Tor SOCKS proxy active  {grey('(127.0.0.1:9050)')}")
    print()
    info("A separate isolated browser profile will be opened.")
    info("Your normal browser and bookmarks are untouched.")
    info("All traffic in this window routes through Tor.")
    print()

    available: list[str] = []
    for name, bins in _BROWSER_BINS.items():
        if any(b and os.path.isfile(b) for b in bins):
            available.append(name)

    if not available:
        err("No supported browsers found.")
        warn("Install Firefox, Chrome, or Brave to use this feature.")
        input(f"\n  {grey('Press Enter to return to menu...')}")
        return

    if len(available) == 1:
        choice_name = available[0]
    else:
        section("Select Browser")
        for i, name in enumerate(available, 1):
            print(f"    {bold(white(f'[{i}]'))}  {bold(name)}")
        print()
        try:
            raw = input(f"  {bold('›')} ").strip()
            idx = int(raw) - 1
            if idx < 0 or idx >= len(available):
                raise ValueError
            choice_name = available[idx]
        except (ValueError, EOFError):
            warn("Invalid choice — returning to menu.")
            time.sleep(1)
            return

    section(f"Launching {choice_name}")
    info(f"Opening isolated {choice_name} window routed through Tor...")
    info("This window will show a Tor exit IP on whatismyip.com")
    print()

    try:
        if choice_name == "Firefox":
            _launch_firefox_private()
        else:
            _launch_chromium_private(choice_name)

        print()
        info("To verify: visit whatismyip.com in this window")
        info("The IP shown will be a Tor exit node, not your real IP")
    except Exception as exc:
        err(f"Failed to launch {choice_name}: {exc}")

    input(f"\n  {grey('Press Enter to return to menu...')}")

MENU_ITEMS = [
    ("1", "Install",        "Set up HIDE and activate all privacy layers",     cmd_install),
    ("2", "Remove",         "Unload daemons and restore system defaults",       cmd_remove),
    ("3", "Reinstall",      "Remove then perform a clean install",              cmd_reinstall),
    ("4", "Status",         "Show running processes and run self-test",         cmd_status),
    ("5", "Private Browser","Open an isolated browser window routed via Tor",  cmd_private_browser),
    ("6", "Dry Run",        "Show what install would do without changing anything", lambda: cmd_dry_run("install")),
    ("7", "Rescue",         "Emergency network restore without uninstalling",    cmd_rescue),
    ("8", "Capabilities",   "Show supported protections on this machine",        cmd_capabilities),
    ("q", "Quit",           "",                                                 None),
]

def main_menu() -> None:
    while True:
        print_banner()
        SI.print_summary()
        section("Main Menu")
        for key, name, desc, _ in MENU_ITEMS:
            if desc:
                print(f"    {bold(cyan(f'[{key}]'))}  {bold(name):<14} {grey(desc)}")
            else:
                print(f"    {bold(cyan(f'[{key}]'))}  {bold(name)}")
        print()
        try:
            choice = input(f"  {bold('›')} ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if choice in {"q", "0", "exit", "quit"}:
            break

        matched = next((fn for k, _, _, fn in MENU_ITEMS if k == choice), None)
        if matched is None:
            warn(f"Unknown option: {choice!r}")
            time.sleep(0.8)
            continue

        needs_install = {cmd_remove, cmd_reinstall, cmd_status, cmd_private_browser}
        if matched in needs_install and not APP_SUPPORT.exists():
            print()
            warn("HIDE is not installed yet.")
            info("Choose option [1] Install first before using this feature.")
            input(f"\n  {grey('Press Enter to return to menu...')}")
            continue

        try:
            matched()
        except KeyboardInterrupt:
            print()
            warn("Interrupted — returning to menu.")
            time.sleep(1)
        except Exception as exc:
            print()
            err(f"Unexpected error: {exc}")
            info("Try reinstalling or check your internet connection.")
            time.sleep(2)

        input(f"\n  {grey('Press Enter to return to menu...')}")

    print_banner()
    print(f"  {bold('Goodbye.')}\n")

def _repair_permissions() -> None:
    if not APP_SUPPORT.exists():
        return
    try:

        test = APP_SUPPORT / ".permission_test"
        test.touch()
        test.unlink()
        return
    except PermissionError:
        pass

    if sys.platform == "win32":
        return
    owner = _owner_spec(SI.uid, SI.gid)
    print(f"  {yellow('!')} Fixing directory permissions (requires password once)...")
    r = subprocess.run(
        ["sudo", "chown", "-R", owner, str(APP_SUPPORT)],
        capture_output=False,
    )
    if r.returncode == 0:
        print(f"  {green('✓')} Permissions fixed.\n")
    else:
        print(f"  {red('✗')} Could not fix permissions automatically.")
        print(f"    Run this command manually and try again:")
        print(f"    {grey(f'sudo chown -R {owner} {APP_SUPPORT}')}\n")
        sys.exit(1)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, lambda *_: (print(), sys.exit(0)))

    auto = "--auto-install" in sys.argv
    rescue = "--rescue" in sys.argv or "rescue" in sys.argv
    dry_run = "--dry-run" in sys.argv
    capabilities = "--capabilities" in sys.argv or "capabilities" in sys.argv
    help_requested = "--help" in sys.argv or "-h" in sys.argv or "help" in sys.argv

    def _dry_run_target() -> str:
        for marker in ("--dry-run", "dry-run"):
            if marker in sys.argv:
                idx = sys.argv.index(marker)
                if idx + 1 < len(sys.argv) and not sys.argv[idx + 1].startswith("-"):
                    return sys.argv[idx + 1]
        return "install"

    if help_requested:
        cmd_help()
        sys.exit(0)

    if not dry_run and not capabilities:
        _repair_permissions()

    if dry_run:
        try:
            cmd_dry_run(_dry_run_target())
        except Exception as exc:
            err(str(exc))
            sys.exit(1)
        sys.exit(0)

    if capabilities:
        cmd_capabilities()
        sys.exit(0)

    with InstanceLock("hide"):
        if rescue:
            try:
                cmd_rescue()
            except Exception as exc:
                err(f"Rescue failed: {exc}")
                sys.exit(1)
        elif auto:
            try:
                cmd_install()
            except Exception as exc:
                err(f"Install failed: {exc}")
                sys.exit(1)
        else:
            main_menu()
