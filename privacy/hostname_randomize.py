                      

import logging
import os
import random
import subprocess
import sys

import _path
from platform_utils import randomize_hostname as _platform_randomize_hostname

log = logging.getLogger(__name__)

_ADJECTIVES = [
    "amber", "arctic", "azure", "brisk", "calm", "cedar", "cold", "crisp",
    "dawn", "deft", "dim", "dusk", "early", "east", "faint", "firm", "fleet",
    "fog", "free", "frost", "grey", "hazy", "idle", "jade", "keen", "lake",
    "lean", "mild", "mist", "mute", "neat", "north", "pale", "pine", "plain",
    "quiet", "rapid", "reed", "sage", "salt", "sand", "serene", "sharp",
    "silent", "slim", "slow", "soft", "still", "stone", "swift", "teal",
    "thin", "tide", "warm", "west", "wide", "wild", "wind",
]
_NOUNS = [
    "arc", "ash", "bay", "beam", "bird", "blade", "brook", "cloud", "coast",
    "creek", "crest", "dawn", "deck", "dew", "drift", "dune", "dust", "edge",
    "fern", "field", "flint", "flow", "foam", "forge", "gate", "glade",
    "glen", "grove", "hill", "hollow", "hull", "isle", "knoll", "lake",
    "leaf", "ledge", "marsh", "mesa", "mill", "moor", "moss", "oak", "path",
    "peak", "pine", "pond", "pool", "raft", "reef", "ridge", "rill", "rise",
    "river", "rock", "root", "sand", "shelf", "shore", "slope", "spur",
    "stem", "stone", "stream", "vale", "wave", "wood",
]

def _random_hostname() -> str:
    adj = random.choice(_ADJECTIVES)
    noun = random.choice(_NOUNS)
    suffix = random.randint(100, 999)
    return f"{adj}-{noun}-{suffix}"

def require_root() -> None:
    if os.geteuid() != 0:
        log.error("hostname_randomize.py requires root.")
        os.execvp("sudo", ["sudo", sys.executable, __file__] + sys.argv[1:])
        sys.exit(1)

def current_names() -> dict[str, str]:
    names: dict[str, str] = {}
    for key in ("ComputerName", "HostName", "LocalHostName"):
        result = subprocess.run(
            ["scutil", f"--get{key}"],
            capture_output=True, text=True,
        )
        names[key] = result.stdout.strip() if result.returncode == 0 else "(unset)"
    return names

def randomize() -> str:
    if os.geteuid() != 0:
        log.debug("Hostname randomization skipped: not root.")
        return ""
    new_name = _platform_randomize_hostname()
    log.info("Hostname randomized → %s", new_name)
    return new_name

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    old = current_names()
    log.info("Old names: %s", old)
    new = randomize()
    log.info("New name:  %s", new)
