

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parent.parent / "config.json"

_DEFAULTS: dict[str, Any] = {
    "tor": {
        "socks_host": "127.0.0.1",
        "socks_port": 9050,
        "control_host": "127.0.0.1",
        "control_port": 9051,
        "dns_port": 5300,
        "bootstrap_timeout_s": 120,
        "bootstrap_poll_s": 2,
        "newnym_cooldown_s": 15,
    },
    "killswitch": {
        "poll_interval_s": 3,
        "socks_probe_timeout_s": 2,
        "pf_anchor": "com.privacy_tool.killswitch",
    },
    "traffic_padding": {
        "min_interval_s": 45,
        "max_interval_s": 180,
        "min_burst": 1,
        "max_burst": 3,
        "request_timeout_s": 10,
        "targets": [
            "https://www.torproject.org/",
            "https://duckduckgo.com/",
        ],
    },
    "log_purge": {
        "max_age_hours": 24,
        "tor_descriptor_max_age_hours": 48,
        "max_file_size_bytes": 1048576,
        "overwrite_passes": 3,
    },
    "dns": {
        "pf_anchor": "com.privacy_tool.dns",
        "resolver_file": "/etc/resolver/privacy_tool_dns",
    },
    "ntp": {
        "sync_sources": ["www.cloudflare.com", "www.google.com"],
        "timeout_s": 15,
        "pf_anchor": "com.privacy_tool.ntp",
    },
    "bridge_rotation": {
        "moat_url": "https://bridges.torproject.org/moat/circumvention/builtin",
        "request_timeout_s": 15,
    },
    "integrity": {
        "watched_extensions": [".py", ".plist", ".sh"],
        "excluded_files": ["integrity_manifest.json", "__pycache__"],
    },
}

def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result

def _load() -> dict[str, Any]:
    if not _CONFIG_PATH.exists():
        log.warning("config.json not found — using defaults.")
        return _DEFAULTS
    try:
        raw = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))

        raw = {k: v for k, v in raw.items() if not k.startswith("_")}
        return _deep_merge(_DEFAULTS, raw)
    except (json.JSONDecodeError, OSError) as exc:
        log.error("Failed to parse config.json (%s) — using defaults.", exc)
        return _DEFAULTS

CFG: dict[str, Any] = _load()

def get(section: str, key: str, default: Any = None) -> Any:
    return CFG.get(section, {}).get(key, default)
