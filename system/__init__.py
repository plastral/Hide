import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import _path

from system.platform_utils  import (
    IS_MACOS, IS_LINUX, IS_WINDOWS, os_name,
    install_package, install_service, remove_service,
    firewall_block, firewall_pass, firewall_block_dns,
    get_active_interfaces, randomize_mac, randomize_hostname,
    disable_system_ntp, block_ntp_port,
    apply_hosts_block, remove_hosts_block,
    app_support_dir, is_admin, real_uid_gid, user_home,
    macos_pf_flush_anchor, macos_pf_load_anchor,
)
from system.process_utils   import set_process_name, InstanceLock, ensure_venv_with_setproctitle
from system.integrity_check import run_check, update_manifest, verify
from system.log_purge       import run as run_log_purge

__all__ = [
    "IS_MACOS", "IS_LINUX", "IS_WINDOWS", "os_name",
    "install_package", "install_service", "remove_service",
    "firewall_block", "firewall_pass", "firewall_block_dns",
    "get_active_interfaces", "randomize_mac", "randomize_hostname",
    "disable_system_ntp", "block_ntp_port",
    "apply_hosts_block", "remove_hosts_block", "app_support_dir",
    "is_admin", "real_uid_gid", "user_home",
    "macos_pf_flush_anchor", "macos_pf_load_anchor",
    "set_process_name", "InstanceLock", "ensure_venv_with_setproctitle",
    "run_check", "update_manifest", "verify",
    "run_log_purge",
]
