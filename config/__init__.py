import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import _path              

from config.config_loader import CFG, get

__all__ = ["CFG", "get"]
