import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import _path              

from browser.webrtc_prevention  import apply_all as apply_webrtc_prevention
from browser.browser_hardening  import launch_firefox, launch_chromium

__all__ = ["apply_webrtc_prevention", "launch_firefox", "launch_chromium"]
