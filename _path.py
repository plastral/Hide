
import sys
from pathlib import Path

ROOT_DIR: Path = Path(__file__).parent

_PACKAGES = ["core", "privacy", "browser", "system", "security", "config"]

_entries_to_manage = {str(ROOT_DIR)} | {str(ROOT_DIR / p) for p in _PACKAGES}
sys.path = [p for p in sys.path if p not in _entries_to_manage]

for _pkg in reversed(_PACKAGES):
    sys.path.insert(0, str(ROOT_DIR / _pkg))

sys.path.append(str(ROOT_DIR))
