import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import _path

from browser.webrtc_prevention import apply_all as apply_webrtc_prevention

__all__ = ["apply_webrtc_prevention"]
