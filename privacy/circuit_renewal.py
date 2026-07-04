

import logging
import threading
import time
from pathlib import Path

import _path
from config_loader import CFG

log = logging.getLogger(__name__)

_INTERVAL_S  = CFG.get("tor", {}).get("circuit_renewal_interval_s", 600)

_stop_event  = threading.Event()

def _renewal_loop() -> None:
    log.info("Circuit renewal started — rotating circuits every %d seconds.", _INTERVAL_S)
    while not _stop_event.wait(timeout=_INTERVAL_S):
        try:
            from tor_control import connect
            ctrl = connect()
            ctrl.new_identity()
            ctrl.close()
            log.info("Tor circuits rotated — new connections will use fresh paths.")
        except Exception as exc:

            log.debug("Circuit rotation skipped this round: %s", exc)

def start() -> threading.Thread:
    t = threading.Thread(
        target=_renewal_loop,
        name="circuit-renewal",
        daemon=True,
    )
    t.start()
    return t

def stop() -> None:
    _stop_event.set()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    log.info("Running circuit renewal in foreground (Ctrl-C to stop).")
    try:
        start().join()
    except KeyboardInterrupt:
        stop()
