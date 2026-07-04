import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import _path

from privacy.mac_randomize      import randomize_all as randomize_mac
from privacy.hostname_randomize import randomize as randomize_hostname
from privacy.dns_leak_prevention import activate as activate_dns, deactivate as deactivate_dns
from privacy.telemetry_block    import activate as activate_telemetry, deactivate as deactivate_telemetry
from privacy.ntp_over_tor       import activate as activate_ntp
from privacy.traffic_padding    import start as start_padding, stop as stop_padding
from privacy.circuit_renewal   import start as start_circuit_renewal, stop as stop_circuit_renewal
from privacy.timezone_utc      import activate as activate_utc, deactivate as deactivate_utc

__all__ = [
    "randomize_mac", "randomize_hostname",
    "activate_dns", "deactivate_dns",
    "activate_telemetry", "deactivate_telemetry",
    "activate_ntp",
    "start_padding", "stop_padding",
    "start_circuit_renewal", "stop_circuit_renewal",
    "activate_utc", "deactivate_utc",
]
