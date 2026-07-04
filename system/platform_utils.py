

import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

_sys = platform.system().lower()
IS_MACOS   = _sys == "darwin"
IS_LINUX   = _sys == "linux"
IS_WINDOWS = _sys == "windows"

def is_admin() -> bool:
    if IS_WINDOWS:
        try:
            import ctypes
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False
    return hasattr(os, "geteuid") and os.geteuid() == 0

def user_home() -> Path:
    if IS_WINDOWS:
        return Path.home()
    sudo_uid = os.environ.get("SUDO_UID")
    if sudo_uid:
        try:
            import pwd
            return Path(pwd.getpwuid(int(sudo_uid)).pw_dir)
        except (ImportError, KeyError, ValueError):
            pass
    return Path.home()

def real_uid_gid() -> tuple[int, int]:
    if IS_WINDOWS:
        return (0, 0)
    return (
        int(os.environ.get("SUDO_UID", os.getuid())),
        int(os.environ.get("SUDO_GID", os.getgid())),
    )

def os_name() -> str:
    if IS_MACOS:   return "macOS"
    if IS_LINUX:   return f"Linux ({_linux_distro()})"
    if IS_WINDOWS: return f"Windows {platform.version()}"
    return platform.system()

def _linux_distro() -> str:
    for f in ["/etc/os-release", "/etc/lsb-release"]:
        p = Path(f)
        if p.exists():
            for line in p.read_text().splitlines():
                if line.startswith("NAME="):
                    return line.split("=", 1)[1].strip().strip('"')
    return "Unknown"

def _linux_pkg_manager() -> Optional[str]:
    for mgr in ["apt-get", "dnf", "pacman", "zypper", "yum"]:
        if shutil.which(mgr):
            return mgr
    return None

def _win_pkg_manager() -> Optional[str]:
    for mgr in ["winget", "choco", "scoop"]:
        if shutil.which(mgr):
            return mgr
    return None

def install_package(package: str, binary: str) -> str:
    existing = shutil.which(binary) or shutil.which(binary + ".exe")
    if existing:
        return existing

    if IS_WINDOWS:
        if package == "tor":
            already = next(_WIN_TOR_DIR.rglob("tor.exe"), None)
            if already:
                os.environ["PATH"] = str(already.parent) + os.pathsep + os.environ.get("PATH", "")
                return str(already)
        elif package == "obfs4proxy":
            already = _find_win_pt_binary()
            if already:
                os.environ["PATH"] = str(Path(already).parent) + os.pathsep + os.environ.get("PATH", "")
                return str(already)

    if IS_MACOS:
        _brew_install(package)
    elif IS_LINUX:
        _linux_install(package)
    elif IS_WINDOWS:
        _windows_install(package, binary)
        if package == "obfs4proxy":
            pt_bin = _find_win_pt_binary()
            if pt_bin:
                return str(pt_bin)
        else:
            win_bin = next(_WIN_TOR_DIR.rglob(binary + ".exe"), None)
            if win_bin:
                return str(win_bin)

    path = shutil.which(binary) or shutil.which(binary + ".exe")
    if not path:
        raise RuntimeError(f"Could not locate '{binary}' after installing '{package}'.")
    return path

def _brew_install(package: str) -> None:
    brew = shutil.which("brew")
    if not brew:
        for candidate in ("/opt/homebrew/bin/brew", "/usr/local/bin/brew"):
            if os.path.isfile(candidate):
                brew = candidate
                break
    if not brew:
        raise RuntimeError(
            "Homebrew not found. Install it from https://brew.sh and try again."
        )
    subprocess.run([brew, "install", package], check=True, capture_output=True)

_LINUX_OBFS4_URL = "https://github.com/yawning/obfs4/releases/download/obfs4proxy-0.0.14/obfs4proxy_linux_amd64"

def _linux_install(package: str) -> None:
    mgr = _linux_pkg_manager()
    if mgr:
        cmds = {
            "apt-get": ["sudo", "apt-get", "install", "-y", "-qq", package],
            "dnf":     ["sudo", "dnf",     "install", "-y", "-q",  package],
            "pacman":  ["sudo", "pacman",  "-S", "--noconfirm", "--needed", package],
            "zypper":  ["sudo", "zypper",  "install", "-y", package],
            "yum":     ["sudo", "yum",     "install", "-y", package],
        }
        result = subprocess.run(cmds[mgr], capture_output=True)
        if result.returncode == 0:
            return

    if package == "obfs4proxy":
        import urllib.request
        dest = Path("/usr/local/bin/obfs4proxy")
        urllib.request.urlretrieve(_LINUX_OBFS4_URL, dest)
        subprocess.run(["chmod", "+x", str(dest)], check=True, capture_output=True)
        return

    if not mgr:
        raise RuntimeError("No supported package manager found.")

def _win_localappdata() -> str:
    v = os.environ.get("LOCALAPPDATA", "")
    if not v:
        app = os.environ.get("APPDATA", "")
        if app:
            v = str(Path(app).parent / "Local")
    if not v:
        v = str(Path.home() / "AppData" / "Local")
    return v

_WIN_TOR_DIR = Path(_win_localappdata()) / "HIDE" / "tor" if IS_WINDOWS else Path("/tmp/hide_tor")
_WIN_TOR_URL = (
    "https://archive.torproject.org/tor-package-archive/torbrowser/14.5.1/"
    "tor-expert-bundle-windows-x86_64-14.5.1.tar.gz"
)

def _windows_install(package: str, binary: str) -> None:
    if package == "tor":
        _windows_download_tor()
    elif package == "obfs4proxy":
        _windows_find_or_extract_obfs4()

def _find_win_pt_binary() -> Path | None:
    for name in ("obfs4proxy.exe", "lyrebird.exe"):
        found = next(_WIN_TOR_DIR.rglob(name), None)
        if found:
            return found
    return None

def _windows_download_tor() -> None:
    import socket as _socket, tarfile, urllib.request, tempfile, sys as _sys
    # urlretrieve has no timeout parameter; without a default socket timeout a
    # stalled connection would hang the whole installer indefinitely.
    _socket.setdefaulttimeout(60)
    _WIN_TOR_DIR.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mktemp(suffix=".tar.gz"))

    last_pct = [-1]
    def _progress(block_count, block_size, total_size):
        if total_size <= 0:
            return
        pct = min(100, int(block_count * block_size * 100 / total_size))
        if pct != last_pct[0] and pct % 5 == 0:
            last_pct[0] = pct
            bar  = "#" * (pct // 5) + "." * (20 - pct // 5)
            _sys.stdout.write(f"\r    Downloading Tor... {pct:>3}%  [{bar}]  ")
            _sys.stdout.flush()

    try:
        urllib.request.urlretrieve(_WIN_TOR_URL, tmp, reporthook=_progress)
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(
            f"Failed to download the Tor Expert Bundle from {_WIN_TOR_URL}: {exc}. "
            "Check your internet connection and try again."
        ) from exc
    finally:
        _socket.setdefaulttimeout(None)
    _sys.stdout.write("\r    Extracting...                                    \n")
    _sys.stdout.flush()

    with tarfile.open(tmp) as tf:
        tf.extractall(_WIN_TOR_DIR)
    tmp.unlink(missing_ok=True)
    tor_bin = next(_WIN_TOR_DIR.rglob("tor.exe"), None)
    if tor_bin:
        os.environ["PATH"] = str(tor_bin.parent) + os.pathsep + os.environ.get("PATH", "")
    pt_bin = _find_win_pt_binary()
    if pt_bin:
        os.environ["PATH"] = str(Path(pt_bin).parent) + os.pathsep + os.environ.get("PATH", "")

def _windows_find_or_extract_obfs4() -> None:
    pt_bin = _find_win_pt_binary()
    if pt_bin:
        os.environ["PATH"] = str(pt_bin.parent) + os.pathsep + os.environ.get("PATH", "")
        return
    _windows_download_tor()

def firewall_block() -> None:
    if IS_MACOS:
        _macos_pf_block()
    elif IS_LINUX:
        _linux_iptables_block()
    elif IS_WINDOWS:
        _windows_fw_block()

def firewall_pass() -> None:
    if IS_MACOS:
        _macos_pf_pass()
    elif IS_LINUX:
        _linux_iptables_pass()
    elif IS_WINDOWS:
        _windows_fw_pass()

def firewall_block_dns() -> None:
    if IS_MACOS:
        _macos_pf_dns()
    elif IS_LINUX:
        _linux_iptables_dns()
    elif IS_WINDOWS:
        _windows_dns_redirect()

def firewall_restore_dns() -> None:
    """Undo the DNS redirect/hijack. Safe to call when nothing was applied."""
    if IS_MACOS:
        macos_pf_flush_anchor("com.privacy_tool.dns")
    elif IS_LINUX:
        subprocess.run(["sudo", "iptables", "-t", "nat", "-D", "OUTPUT", "-p", "udp",
                        "--dport", "53", "-j", "REDIRECT", "--to-ports", "5300"],
                       capture_output=True)
        subprocess.run(["sudo", "iptables", "-t", "nat", "-D", "OUTPUT", "-p", "tcp",
                        "--dport", "53", "-j", "REDIRECT", "--to-ports", "5300"],
                       capture_output=True)
        _linux_restore_resolv_conf()
    elif IS_WINDOWS:
        _windows_restore_dns()

_PF_HIDE_BASE = """\
scrub-anchor "com.apple/*"
nat-anchor "com.apple/*"
rdr-anchor "com.apple/*"
dummynet-anchor "com.apple/*"
anchor "com.apple/*"
load anchor "com.apple" from "/etc/pf.anchors/com.apple"

rdr-anchor "com.privacy_tool.dns"
anchor "com.privacy_tool.killswitch"
anchor "com.privacy_tool.dns"
anchor "com.privacy_tool.telemetry"
anchor "com.privacy_tool.ntp"
"""

_PF_BLOCK = """\
block drop out quick on ! lo0 all
block drop in  quick on ! lo0 all
pass on lo0 all
"""
_PF_PASS = "pass all\n"
_PF_DNS = """\
rdr pass proto udp from any to !127.0.0.1 port 53 -> 127.0.0.1 port 5300
rdr pass proto tcp from any to !127.0.0.1 port 53 -> 127.0.0.1 port 5300
block drop quick inet6 all
block drop quick proto udp from any to any port 53
"""

def _macos_pf_base_loaded() -> bool:
    rules = subprocess.run(["pfctl", "-sr"], capture_output=True, text=True)
    nat = subprocess.run(["pfctl", "-sn"], capture_output=True, text=True)
    required_rules = [
        'anchor "com.privacy_tool.killswitch"',
        'anchor "com.privacy_tool.dns"',
        'anchor "com.privacy_tool.telemetry"',
        'anchor "com.privacy_tool.ntp"',
    ]
    return (
        rules.returncode == 0
        and nat.returncode == 0
        and all(anchor in rules.stdout for anchor in required_rules)
        and 'rdr-anchor "com.privacy_tool.dns"' in nat.stdout
    )

def _macos_pf_ensure_base() -> None:
    if not _macos_pf_base_loaded():
        subprocess.run(["pfctl", "-f", "-"], input=_PF_HIDE_BASE, text=True, capture_output=True)

def macos_pf_load_anchor(anchor: str, rules: str) -> subprocess.CompletedProcess:
    _macos_pf_ensure_base()
    proc = subprocess.run(
        ["pfctl", "-a", anchor, "-f", "-"],
        input=rules,
        text=True,
        capture_output=True,
    )
    subprocess.run(["pfctl", "-e"], capture_output=True)
    return proc

def macos_pf_flush_anchor(anchor: str) -> subprocess.CompletedProcess:
    return subprocess.run(["pfctl", "-a", anchor, "-F", "all"], capture_output=True)

def _macos_pf_block():
    macos_pf_load_anchor("com.privacy_tool.killswitch", _PF_BLOCK)

def _macos_pf_pass():
    macos_pf_load_anchor("com.privacy_tool.killswitch", _PF_PASS)

def _macos_pf_dns():
    macos_pf_load_anchor("com.privacy_tool.dns", _PF_DNS)

def _linux_persist_iptables() -> None:
    iptables_dir = Path("/etc/iptables")
    subprocess.run(["sudo", "mkdir", "-p", str(iptables_dir)], capture_output=True)
    saved = subprocess.run(
        ["sudo", "sh", "-c", "iptables-save > /etc/iptables/rules.v4"],
        capture_output=True,
    )
    subprocess.run(
        ["sudo", "sh", "-c", "ip6tables-save > /etc/iptables/rules.v6"],
        capture_output=True,
    )
    if saved.returncode != 0:
        subprocess.run(["sudo", "netfilter-persistent", "save"], capture_output=True)

def _linux_iptables_block():
    for cmd in [
        ["iptables", "-I", "OUTPUT", "1", "!", "-o", "lo", "-j", "DROP"],
        ["iptables", "-I", "INPUT",  "1", "!", "-i", "lo", "-j", "DROP"],
        ["ip6tables", "-I", "OUTPUT", "1", "-j", "DROP"],
        ["ip6tables", "-I", "INPUT",  "1", "-j", "DROP"],
    ]:
        subprocess.run(["sudo"] + cmd, capture_output=True)
    _linux_persist_iptables()

def _linux_iptables_pass():
    for cmd in [
        ["iptables",  "-D", "OUTPUT", "!", "-o", "lo", "-j", "DROP"],
        ["iptables",  "-D", "INPUT",  "!", "-i", "lo", "-j", "DROP"],
        ["ip6tables", "-D", "OUTPUT", "-j", "DROP"],
        ["ip6tables", "-D", "INPUT",  "-j", "DROP"],
    ]:
        subprocess.run(["sudo"] + cmd, capture_output=True)
    _linux_restore_resolv_conf()

def _linux_restore_resolv_conf() -> None:
    backup = Path("/etc/resolv.conf.hide_backup")
    if backup.exists():
        subprocess.run(
            ["sudo", "cp", str(backup), "/etc/resolv.conf"],
            capture_output=True,
        )
        subprocess.run(["sudo", "rm", "-f", str(backup)], capture_output=True)

def _linux_iptables_dns():
    for cmd in [
        ["iptables", "-t", "nat", "-I", "OUTPUT", "1", "-p", "udp",
         "--dport", "53", "-j", "REDIRECT", "--to-ports", "5300"],
        ["iptables", "-t", "nat", "-I", "OUTPUT", "1", "-p", "tcp",
         "--dport", "53", "-j", "REDIRECT", "--to-ports", "5300"],
        ["ip6tables", "-I", "OUTPUT", "1", "-j", "DROP"],
    ]:
        subprocess.run(["sudo"] + cmd, capture_output=True)

    backup = Path("/etc/resolv.conf.hide_backup")
    if not backup.exists():
        subprocess.run(
            ["sudo", "cp", "/etc/resolv.conf", str(backup)],
            capture_output=True,
        )

    is_active = subprocess.run(
        ["systemctl", "is-active", "systemd-resolved"],
        capture_output=True, text=True,
    )
    if is_active.stdout.strip() == "active":
        iface_result = subprocess.run(
            ["sh", "-c", "ip route get 1 | awk '{print $5; exit}'"],
            capture_output=True, text=True,
        )
        main_interface = iface_result.stdout.strip()
        if main_interface:
            subprocess.run(
                ["sudo", "systemd-resolve", "--set-dns=127.0.0.1",
                 "--set-domain=.", f"--interface={main_interface}"],
                capture_output=True,
            )
        resolved_conf_dir = Path("/etc/systemd/resolved.conf.d")
        subprocess.run(["sudo", "mkdir", "-p", str(resolved_conf_dir)], capture_output=True)
        resolved_conf_content = "[Resolve]\nDNS=127.0.0.1\nDomains=~.\nDNSStubListener=no\n"
        tmp_resolved = Path("/tmp/hide_resolved.conf")
        tmp_resolved.write_text(resolved_conf_content)
        subprocess.run(
            ["sudo", "mv", str(tmp_resolved), str(resolved_conf_dir / "hide.conf")],
            capture_output=True,
        )
    else:
        subprocess.run(
            ["sudo", "sh", "-c", "echo 'nameserver 127.0.0.1' > /etc/resolv.conf"],
            capture_output=True,
        )

def disable_ipv6_windows() -> None:
    subprocess.run(
        ["netsh", "advfirewall", "firewall", "add", "rule",
         "name=HIDE_block_ipv6", "dir=out", "action=block",
         "protocol=any", "remoteip=::/0"],
        capture_output=True,
    )
    try:
        import winreg
        ipv6_key_path = r"SYSTEM\CurrentControlSet\Services\Tcpip6\Parameters"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, ipv6_key_path, 0,
                            winreg.KEY_READ | winreg.KEY_WRITE) as key:
            winreg.SetValueEx(key, "DisabledComponents", 0, winreg.REG_DWORD, 0xff)
    except Exception:
        pass

def _reenable_ipv6_windows() -> None:
    subprocess.run(
        ["netsh", "advfirewall", "firewall", "delete", "rule", "name=HIDE_block_ipv6"],
        capture_output=True,
    )
    try:
        import winreg
        ipv6_key_path = r"SYSTEM\CurrentControlSet\Services\Tcpip6\Parameters"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, ipv6_key_path, 0,
                            winreg.KEY_READ | winreg.KEY_WRITE) as key:
            winreg.SetValueEx(key, "DisabledComponents", 0, winreg.REG_DWORD, 0x0)
    except Exception:
        pass

def _windows_fw_block():
    for cmd in [
        ["netsh", "advfirewall", "firewall", "add", "rule",
         "name=HIDE_block_out", "dir=out", "action=block",
         "remoteip=1.0.0.0-255.255.255.255"],
        ["netsh", "advfirewall", "firewall", "add", "rule",
         "name=HIDE_block_in", "dir=in", "action=block",
         "remoteip=1.0.0.0-255.255.255.255"],
    ]:
        subprocess.run(cmd, capture_output=True)
    disable_ipv6_windows()

def _windows_fw_pass():
    for rule in ["HIDE_block_out", "HIDE_block_in"]:
        subprocess.run(
            ["netsh", "advfirewall", "firewall", "delete", "rule", f"name={rule}"],
            capture_output=True,
        )
    _reenable_ipv6_windows()

def _parse_connected_interfaces(netsh_output: str) -> list[str]:
    adapters: list[str] = []
    for line in netsh_output.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[1] == "Connected":
            adapters.append(" ".join(parts[3:]))
    return adapters

def _windows_dns_redirect():
    adapters_file = app_support_dir() / "original_dns_adapters.txt"
    app_support_dir().mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        ["netsh", "interface", "show", "interface"],
        capture_output=True, text=True,
    )
    connected_adapters = _parse_connected_interfaces(result.stdout)

    adapters_file.write_text("\n".join(connected_adapters), encoding="utf-8")

    for adapter_name in connected_adapters:
        subprocess.run(
            ["netsh", "interface", "ip", "set", "dns",
             f"name={adapter_name}", "static", "127.0.0.1"],
            capture_output=True,
        )

    for proto in ("UDP", "TCP"):
        subprocess.run(
            ["netsh", "advfirewall", "firewall", "add", "rule",
             f"name=HIDE_block_dns_{proto.lower()}", "dir=out", "action=block",
             f"protocol={proto}", "remoteport=53"],
            capture_output=True,
        )

def _windows_restore_dns():
    adapters_file = app_support_dir() / "original_dns_adapters.txt"
    if adapters_file.exists():
        adapter_names = [
            line.strip()
            for line in adapters_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        for adapter_name in adapter_names:
            subprocess.run(
                ["netsh", "interface", "ip", "set", "dns",
                 f"name={adapter_name}", "dhcp"],
                capture_output=True,
            )
        adapters_file.unlink(missing_ok=True)

    for rule in ("HIDE_block_dns", "HIDE_block_dns_udp", "HIDE_block_dns_tcp"):
        subprocess.run(
            ["netsh", "advfirewall", "firewall", "delete", "rule", f"name={rule}"],
            capture_output=True,
        )

TOOL_DIR = Path(__file__).parent

def install_service(name: str, description: str, python_path: str, script_path: str) -> None:
    if IS_MACOS:
        _macos_install_service(name, python_path, script_path)
    elif IS_LINUX:
        _linux_install_service(name, description, python_path, script_path)
    elif IS_WINDOWS:
        _windows_install_service(name, description, python_path, script_path)

def remove_service(name: str) -> None:
    if IS_MACOS:
        _macos_remove_service(name)
    elif IS_LINUX:
        _linux_remove_service(name)
    elif IS_WINDOWS:
        _windows_remove_service(name)

def _macos_plist_path(name: str) -> Path:
    return Path("/Library/LaunchDaemons") / f"{name}.plist"

def _macos_install_service(name: str, python_path: str, script_path: str) -> None:
    app_support = app_support_dir()
    app_support.mkdir(parents=True, exist_ok=True)
    uid, gid = real_uid_gid()
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>{name}</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>ProgramArguments</key>
  <array>
    <string>{python_path}</string>
    <string>{script_path}</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>HOME</key><string>{user_home()}</string>
    <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>SUDO_UID</key><string>{uid}</string>
    <key>SUDO_GID</key><string>{gid}</string>
  </dict>
  <key>StandardOutPath</key>
  <string>{app_support}/launchd_stdout.log</string>
  <key>StandardErrorPath</key>
  <string>{app_support}/launchd_stderr.log</string>
  <key>SoftResourceLimits</key>
  <dict><key>NumberOfFiles</key><integer>256</integer></dict>
</dict></plist>"""
    dst = _macos_plist_path(name)
    tmp = Path(f"/tmp/{name}.plist")
    tmp.write_text(plist)
    subprocess.run(["sudo", "cp", str(tmp), str(dst)], check=True, capture_output=True)
    subprocess.run(["sudo", "chown", "root:wheel", str(dst)], capture_output=True)
    subprocess.run(["sudo", "chmod", "644", str(dst)], capture_output=True)
    tmp.unlink(missing_ok=True)

    r = subprocess.run(["sudo", "launchctl", "bootstrap", "system", str(dst)],
                       capture_output=True, text=True)
    if r.returncode != 0 and "already" not in (r.stdout + r.stderr).lower():
        subprocess.run(["sudo", "launchctl", "load", "-w", str(dst)], capture_output=True)

def _macos_remove_service(name: str) -> None:
    dst = _macos_plist_path(name)
    subprocess.run(["sudo", "launchctl", "bootout", "system", str(dst)], capture_output=True)
    subprocess.run(["sudo", "launchctl", "unload", "-w", str(dst)], capture_output=True)
    subprocess.run(["sudo", "rm", "-f", str(dst)], capture_output=True)

def _linux_service_path(name: str) -> Path:
    return Path(f"/etc/systemd/system/{name}.service")

def _linux_install_service(name: str, description: str, python_path: str, script_path: str) -> None:
    app_dir = app_support_dir()
    app_dir.mkdir(parents=True, exist_ok=True)
    unit = f"""[Unit]
Description={description}
After=network.target
Wants=network.target

[Service]
Type=simple
ExecStart={python_path} {script_path}
Restart=always
RestartSec=10
Environment=HOME={user_home()}
Environment=PATH=/usr/local/bin:/usr/bin:/bin
StandardOutput=append:{app_dir}/{name}.log
StandardError=append:{app_dir}/{name}.log

[Install]
WantedBy=multi-user.target
"""
    dst = _linux_service_path(name)
    tmp = Path(f"/tmp/{name}.service")
    tmp.write_text(unit)
    subprocess.run(["sudo", "mv", str(tmp), str(dst)], check=True, capture_output=True)
    subprocess.run(["sudo", "systemctl", "daemon-reload"], capture_output=True)
    subprocess.run(["sudo", "systemctl", "enable", "--now", name], check=True, capture_output=True)

def _linux_remove_service(name: str) -> None:
    subprocess.run(["sudo", "systemctl", "stop",    name], capture_output=True)
    subprocess.run(["sudo", "systemctl", "disable", name], capture_output=True)
    dst = _linux_service_path(name)
    subprocess.run(["sudo", "rm", "-f", str(dst)], capture_output=True)
    subprocess.run(["sudo", "systemctl", "daemon-reload"], capture_output=True)

def _windows_install_service(name: str, description: str, python_path: str, script_path: str) -> None:
    # Both paths routinely contain spaces (e.g. C:\Users\Jane Doe\...), so the
    # program and its argument each need their own quoting inside /TR. schtasks
    # requires the inner double-quotes to be escaped as \" within the /TR value.
    tr_value = f'\\"{python_path}\\" \\"{script_path}\\"'
    subprocess.run(
        ["schtasks", "/Create", "/TN", f"HIDE\\{name}", "/TR", tr_value,
         "/SC", "ONSTART", "/RU", "SYSTEM", "/RL", "HIGHEST", "/F"],
        capture_output=True, text=True,
    )
    subprocess.run(["schtasks", "/Run", "/TN", f"HIDE\\{name}"], capture_output=True)

def _windows_remove_service(name: str) -> None:
    subprocess.run(f'schtasks /Delete /TN "HIDE\\{name}" /F', shell=True, capture_output=True)

def randomize_mac(interface: str) -> Optional[str]:
    import random
    first = (random.randint(0, 255) & 0xFE) | 0x02
    mac   = ":".join(f"{b:02x}" for b in [first] + [random.randint(0, 255) for _ in range(5)])

    if IS_MACOS:
        subprocess.run(["ifconfig", interface, "down"], capture_output=True)
        subprocess.run(["ifconfig", interface, "ether", mac], capture_output=True)
        subprocess.run(["ifconfig", interface, "up"], capture_output=True)
    elif IS_LINUX:
        subprocess.run(["sudo", "ip", "link", "set", interface, "down"], capture_output=True)
        subprocess.run(["sudo", "ip", "link", "set", interface, "address", mac], capture_output=True)
        subprocess.run(["sudo", "ip", "link", "set", interface, "up"], capture_output=True)
    elif IS_WINDOWS:

        import winreg
        key_path = (
            r"SYSTEM\CurrentControlSet\Control\Class"
            r"\{4D36E972-E325-11CE-BFC1-08002BE10318}"
        )
        mac_nodash = mac.replace(":", "")
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path, 0,
                                winreg.KEY_READ | winreg.KEY_WRITE) as key:
                winreg.SetValueEx(key, "NetworkAddress", 0, winreg.REG_SZ, mac_nodash)
        except Exception:
            pass

        subprocess.run(
            ["netsh", "interface", "set", "interface",
             f"name={interface}", "admin=disable"],
            capture_output=True,
        )
        time.sleep(1)
        subprocess.run(
            ["netsh", "interface", "set", "interface",
             f"name={interface}", "admin=enable"],
            capture_output=True,
        )

    return mac

def get_active_interfaces() -> list[str]:
    if IS_MACOS:
        r = subprocess.run(["networksetup", "-listallhardwareports"],
                           capture_output=True, text=True)
        ifaces, current_ok = [], False
        for line in r.stdout.splitlines():
            l = line.strip()
            if l.startswith("Hardware Port:"):
                current_ok = any(k in l.lower() for k in ("wi-fi","ethernet","thunderbolt"))
            elif l.startswith("Device:") and current_ok:
                ifaces.append(l.split(":",1)[1].strip())
        return ifaces
    elif IS_LINUX:
        r = subprocess.run(["ip", "-o", "link", "show"], capture_output=True, text=True)
        return [
            m.group(1) for line in r.stdout.splitlines()
            if (m := re.match(r"\d+:\s+(\w+):", line)) and m.group(1) != "lo"
        ]
    elif IS_WINDOWS:
        r = subprocess.run(
            ["netsh", "interface", "show", "interface"],
            capture_output=True, text=True,
        )
        return _parse_connected_interfaces(r.stdout)
    return []

def randomize_hostname() -> str:
    import random
    adj  = random.choice(["amber","arctic","crisp","calm","frost","jade","quiet","swift","teal","wild"])
    noun = random.choice(["arc","bay","drift","edge","grove","hill","lake","peak","reef","stone"])
    name = f"{adj}-{noun}-{random.randint(100,999)}"

    if IS_MACOS:
        for cmd in ["ComputerName", "HostName", "LocalHostName"]:
            subprocess.run(["scutil", f"--set{cmd}", name], capture_output=True)
    elif IS_LINUX:
        subprocess.run(["sudo", "hostnamectl", "set-hostname", name], capture_output=True)
        Path("/etc/hostname").write_text(name + "\n") if os.geteuid() == 0 else \
            subprocess.run(["sudo", "sh", "-c", f"echo {name} > /etc/hostname"], capture_output=True)
    elif IS_WINDOWS:
        # wmic was removed in recent Windows 11 builds; Rename-Computer is the
        # supported path. The new name takes effect after the next reboot.
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"Rename-Computer -NewName '{name}' -Force"],
            capture_output=True,
        )
    return name

def disable_system_ntp() -> None:
    if IS_MACOS:
        for svc in ["com.apple.timed"]:
            subprocess.run(
                ["sudo", "launchctl", "unload", "-w",
                 f"/System/Library/LaunchDaemons/{svc}.plist"],
                capture_output=True,
            )
    elif IS_LINUX:
        subprocess.run(["sudo", "timedatectl", "set-ntp", "false"], capture_output=True)
        subprocess.run(["sudo", "systemctl", "stop", "systemd-timesyncd"], capture_output=True)
        subprocess.run(["sudo", "systemctl", "stop", "ntp"], capture_output=True)
        subprocess.run(["sudo", "systemctl", "stop", "chrony"], capture_output=True)
    elif IS_WINDOWS:
        subprocess.run(["sc", "stop", "w32tm"], capture_output=True)
        subprocess.run(["sc", "config", "w32tm", "start=disabled"], capture_output=True)

def block_ntp_port() -> None:
    if IS_MACOS:
        rules = "block drop quick proto udp from any to any port 123\n"
        macos_pf_load_anchor("com.privacy_tool.ntp", rules)
    elif IS_LINUX:
        subprocess.run(["sudo", "iptables", "-I", "OUTPUT", "1", "-p", "udp",
                        "--dport", "123", "-j", "DROP"], capture_output=True)
    elif IS_WINDOWS:
        subprocess.run(
            ["netsh", "advfirewall", "firewall", "add", "rule",
             "name=HIDE_block_ntp", "dir=out", "action=block",
             "protocol=UDP", "localport=123"],
            capture_output=True,
        )

def hosts_file() -> Path:
    if IS_WINDOWS:
        return Path(r"C:\Windows\System32\drivers\etc\hosts")
    return Path("/etc/hosts")

def apply_hosts_block(domains: list[str]) -> None:
    marker_start = "BEGIN privacy_tool telemetry block"
    marker_end   = "END privacy_tool telemetry block"
    hf = hosts_file()

    try:
        content = hf.read_text(encoding="utf-8", errors="replace")
    except PermissionError:
        content = ""

    lines, inside = [], False
    for line in content.splitlines(keepends=True):
        if line.strip() == marker_start:  inside = True
        elif line.strip() == marker_end:  inside = False
        elif not inside:                  lines.append(line)

    block = marker_start + "\n"
    block += "\n".join(f"0.0.0.0 {d}" for d in domains) + "\n"
    block += marker_end + "\n"
    new_content = "".join(lines).rstrip("\n") + "\n\n" + block

    if IS_WINDOWS or os.geteuid() == 0:
        hf.write_text(new_content, encoding="utf-8")
    else:
        import tempfile
        tmp = Path(tempfile.mktemp())
        tmp.write_text(new_content, encoding="utf-8")
        subprocess.run(["sudo", "cp", str(tmp), str(hf)], check=True, capture_output=True)
        tmp.unlink(missing_ok=True)

def remove_hosts_block() -> None:
    hf = hosts_file()
    try:
        content = hf.read_text(encoding="utf-8", errors="replace")
    except PermissionError:
        return
    marker_start = "BEGIN privacy_tool telemetry block"
    marker_end   = "END privacy_tool telemetry block"
    lines, inside = [], False
    for line in content.splitlines(keepends=True):
        if line.strip() == marker_start:  inside = True
        elif line.strip() == marker_end:  inside = False
        elif not inside:                  lines.append(line)
    cleaned = "".join(lines)
    if IS_WINDOWS or os.geteuid() == 0:
        hf.write_text(cleaned, encoding="utf-8")
    else:
        import tempfile
        tmp = Path(tempfile.mktemp())
        tmp.write_text(cleaned, encoding="utf-8")
        subprocess.run(["sudo", "cp", str(tmp), str(hf)], capture_output=True)
        tmp.unlink(missing_ok=True)

def app_support_dir() -> Path:
    if IS_MACOS:
        return user_home() / "Library" / "Application Support" / "privacy_tool"
    elif IS_LINUX:
        return Path(os.environ.get("XDG_DATA_HOME",
                    user_home() / ".local" / "share")) / "privacy_tool"
    elif IS_WINDOWS:
        localappdata = os.environ.get("LOCALAPPDATA", "")
        if not localappdata:
            appdata = os.environ.get("APPDATA", "")
            if appdata:
                localappdata = str(Path(appdata).parent / "Local")
        if not localappdata:
            localappdata = str(Path.home() / "AppData" / "Local")
        return Path(localappdata) / "HIDE"
    return Path.home() / ".privacy_tool"
