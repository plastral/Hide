                      

import argparse
import hashlib
import json
import logging
import sys
from pathlib import Path

import _path
from platform_utils import app_support_dir
from config_loader import CFG

log = logging.getLogger(__name__)

TOOL_DIR      = Path(__file__).parent.parent
APP_SUPPORT   = app_support_dir()
MANIFEST_PATH = TOOL_DIR / "integrity_manifest.json"

_WATCHED_EXTS    = set(CFG["integrity"]["watched_extensions"])
_EXCLUDED_FILES  = set(CFG["integrity"]["excluded_files"])

_RUNTIME_EXCLUDED = {
    "config.json",                                           
    "integrity_manifest.json",
}

def _should_watch(f: Path) -> bool:
    if f.name in _EXCLUDED_FILES or f.name in _RUNTIME_EXCLUDED:
        return False
    if f.suffix not in _WATCHED_EXTS:
        return False
    if f.name.startswith("__"):
        return False
    return True

def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def _collect(tool_dir: Path) -> dict[str, str]:
    result = {}
    for f in sorted(tool_dir.rglob("*")):
        if f.is_file() and _should_watch(f) and "__pycache__" not in f.parts and ".venv" not in f.parts:
            relative = str(f.relative_to(tool_dir))
            result[relative] = _hash_file(f)
    return result

def update_manifest() -> None:
    APP_SUPPORT.mkdir(parents=True, exist_ok=True)
    manifest = _collect(TOOL_DIR)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    log.info("Integrity manifest written (%d file(s)).", len(manifest))
    for name, digest in manifest.items():
        log.info("  %s...  %s", digest[:16], name)

def verify() -> bool:
    if not MANIFEST_PATH.exists():
        log.error(
            "Manifest not found at %s. Run: python3 integrity_check.py --update",
            MANIFEST_PATH,
        )
        return False

    stored: dict[str, str] = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    current = _collect(TOOL_DIR)
    ok = True

    for name, expected in stored.items():
        got = current.get(name)
        if got is None:
            log.critical("INTEGRITY FAIL — removed: %s", name)
            ok = False
        elif got != expected:
            log.critical(
                "INTEGRITY FAIL — modified: %s\n  expected: %s\n  got:      %s",
                name, expected, got,
            )
            ok = False

    for name in current:
        if name not in stored:
            log.warning("New unwatched file: %s (run --update if intentional)", name)

    if ok:
        log.info("Integrity check passed (%d file(s)).", len(stored))
    return ok

def run_check(halt_on_failure: bool = True) -> bool:
    if not MANIFEST_PATH.exists():
        log.info("No integrity manifest found — skipping check on first run.")
        return True
    result = verify()
    if not result and halt_on_failure:
        log.critical(
            "Halting — integrity check failed. "
            "After reviewing changes run: python3 integrity_check.py --update"
        )
        sys.exit(2)
    return result

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--update", action="store_true", help="Record current state as trusted")
    args = parser.parse_args()
    if args.update:
        update_manifest()
    else:
        sys.exit(0 if verify() else 1)
