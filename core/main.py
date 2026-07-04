

import logging
import logging.handlers
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).parent.parent))
import _path

from config_loader import CFG
from process_utils import set_process_name, InstanceLock

set_process_name("HIDE Guard")
import integrity_check
import mac_randomize
import hostname_randomize
import dns_leak_prevention
import telemetry_block
import tor_updater
import tor_setup
import bridge_rotation
import tor_bootstrap
import ntp_over_tor
import tor_control
import traffic_padding
import circuit_renewal
import webrtc_prevention
import killswitch
import sip_check
import swap_check
import timezone_utc

from platform_utils import app_support_dir, is_admin, real_uid_gid
APP_SUPPORT = app_support_dir()
APP_SUPPORT.mkdir(parents=True, exist_ok=True)

LOG_MAX_BYTES = CFG["log_purge"]["max_file_size_bytes"]
LOG_BACKUP_COUNT = 2

def _setup_logging() -> None:
    main_log = APP_SUPPORT / "main.log"
    handler_file = logging.handlers.RotatingFileHandler(
        main_log,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler_stdout = logging.StreamHandler(sys.stdout)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    handler_file.setFormatter(fmt)
    handler_stdout.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler_file)
    root.addHandler(handler_stdout)

_setup_logging()
log = logging.getLogger(__name__)

def require_root() -> None:
    if not is_admin():
        log.error("main.py must run with elevated privileges.")
        sys.exit(1)

def _step(n: int, label: str) -> None:
    log.info("=" * 50)
    log.info("Step %d: %s", n, label)

def _log_rotation_watchdog() -> None:
    while True:
        try:
            for log_file in APP_SUPPORT.glob("*.log"):
                if log_file.stat().st_size > LOG_MAX_BYTES:

                    keep = LOG_MAX_BYTES // 2
                    content = log_file.read_bytes()
                    log_file.write_bytes(content[-keep:])
                    log.info("Rotated %s (was %d bytes).", log_file.name, len(content))
        except Exception as exc:
            log.debug("Log rotation watchdog error: %s", exc)
        time.sleep(300)

_watched_threads: list[tuple[str, callable]] = []

def _register_thread(name: str, factory: callable) -> threading.Thread:
    t = factory()
    _watched_threads.append((name, factory))
    return t

def _thread_watchdog() -> None:
    while True:
        time.sleep(30)
        live_names = {t.name for t in threading.enumerate()}
        for name, factory in _watched_threads:
            if name not in live_names:
                log.warning("Thread '%s' died — restarting.", name)
                try:
                    factory()
                except Exception as exc:
                    log.error("Failed to restart thread '%s': %s", name, exc)

def main() -> None:
    require_root()
    uid, gid = real_uid_gid()

    _step(1, "Integrity check")
    integrity_check.run_check(halt_on_failure=True)

    _step(2, "SIP integrity check")
    try:
        sip_check.enforce(halt_on_disabled=CFG.get("security", {}).get(
            "sip_check_halt_on_disabled", False))
    except Exception as exc:
        log.warning("SIP check (non-fatal): %s", exc)

    _step(3, "Parallel boot steps: MAC / hostname / DNS / telemetry")

    def _mac():
        try:
            mac_randomize.randomize_all()
        except Exception as exc:
            log.error("MAC randomization (non-fatal): %s", exc)

    def _hostname():
        try:
            hostname_randomize.randomize()
        except Exception as exc:
            log.error("Hostname randomization (non-fatal): %s", exc)

    def _dns():
        try:
            dns_leak_prevention.activate()
        except Exception as exc:
            log.error("DNS + STUN leak prevention (non-fatal): %s", exc)

    def _telemetry():
        try:
            telemetry_block.activate()
        except Exception as exc:
            log.error("Telemetry blocking (non-fatal): %s", exc)

    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="boot") as pool:
        futures = {pool.submit(fn): fn.__name__ for fn in [_mac, _hostname, _dns, _telemetry]}
        for fut in as_completed(futures):
            if (exc := fut.exception()):
                log.error("Boot step failed: %s", exc)

    _step(7, "Swap encryption check")
    try:
        result = swap_check.check()
        if not result.get("safe"):
            log.warning("Swap/disk not fully encrypted — see log for details.")
    except Exception as exc:
        log.warning("Swap check (non-fatal): %s", exc)

    _step(8, "Timezone → UTC")
    try:
        if CFG.get("security", {}).get("force_utc_timezone", True):
            timezone_utc.activate()
    except Exception as exc:
        log.warning("Timezone (non-fatal): %s", exc)

    _step(9, "Tor version update")
    try:
        tor_updater.check_and_upgrade(uid, gid)
    except Exception as exc:
        log.warning("Tor update (non-fatal): %s", exc)

    _step(10, "Tor / obfs4 setup")
    try:
        kwargs = {}
        if sys.platform != "win32":
            kwargs["preexec_fn"] = lambda: (os.setgid(gid), os.setuid(uid))
        subprocess.run(
            [sys.executable, str(Path(__file__).parent.parent / "core" / "tor_setup.py")],
            check=True,
            **kwargs,
        )
    except Exception as exc:
        log.error("Tor setup failed: %s", exc)
        sys.exit(1)

    _step(11, "Bridge rotation")
    try:
        bridges = bridge_rotation.rotate()
        log.info("Active bridges: %d", len(bridges))
    except Exception as exc:
        log.warning("Bridge rotation (non-fatal): %s", exc)

    _step(12, "Starting Tor")
    torrc = APP_SUPPORT / "torrc"
    try:
        tor_bin = tor_setup._find_tor_bin()
    except FileNotFoundError:
        tor_bin = "tor"
    popen_kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if sys.platform == "win32":
        popen_kwargs["cwd"] = str(Path(tor_bin).parent)
    else:
        popen_kwargs["preexec_fn"] = lambda: (os.setgid(gid), os.setuid(uid))
    tor_proc = subprocess.Popen([tor_bin, "-f", str(torrc)], **popen_kwargs)
    log.info("Tor PID: %d", tor_proc.pid)

    _step(13, "Waiting for Tor bootstrap")
    if not tor_bootstrap.wait_for_bootstrap():
        log.warning("Bootstrap timeout — kill-switch will hold until Tor is ready.")

    _step(14, "NTP over Tor")
    try:
        ntp_over_tor.activate()
    except Exception as exc:
        log.warning("NTP sync (non-fatal): %s", exc)

    _step(15, "Tor control monitor")
    try:
        tor_control.run_monitor()
    except Exception as exc:
        log.warning("Control monitor (non-fatal): %s", exc)

    _step(16, "Circuit renewal scheduler")
    try:
        circuit_renewal.start()
        _watched_threads.append(("circuit-renewal", circuit_renewal.start))
    except Exception as exc:
        log.warning("Circuit renewal (non-fatal): %s", exc)

    _step(17, "Traffic padding")
    try:
        traffic_padding.start()
        _watched_threads.append(("traffic-padding", traffic_padding.start))
    except Exception as exc:
        log.warning("Traffic padding (non-fatal): %s", exc)

    _step(18, "WebRTC and browser hardening")
    try:
        webrtc_prevention.apply_all()
    except Exception as exc:
        log.warning("Browser hardening (non-fatal): %s", exc)

    _step(19, "Log rotation watchdog")
    t_log = threading.Thread(
        target=_log_rotation_watchdog,
        name="log-rotation-watchdog",
        daemon=True,
    )
    t_log.start()

    _step(20, "Thread watchdog")
    t_watch = threading.Thread(
        target=_thread_watchdog,
        name="thread-watchdog",
        daemon=True,
    )
    t_watch.start()

    _step(21, "Kill-switch monitor")
    killswitch.run(pid_file=None)

if __name__ == "__main__":
    with InstanceLock("main"):
        main()
