                      

import ctypes
import ctypes.util
import errno
import os
import sys
from pathlib import Path

import _path
from platform_utils import app_support_dir

if sys.platform != 'win32':
    import fcntl

APP_SUPPORT = app_support_dir()

_TOOL_DIR = Path(__file__).parent.parent                
_VENV_DIR = _TOOL_DIR / ".venv"

def ensure_venv_with_setproctitle() -> str:
    import subprocess as _sp

    if sys.platform == "win32":
        venv_python = _VENV_DIR / "Scripts" / "python.exe"
    else:
        venv_python = _VENV_DIR / "bin" / "python3"

    if not _VENV_DIR.exists():
        _sp.run([sys.executable, "-m", "venv", str(_VENV_DIR)], check=True, capture_output=True)

    _sp.run(
        [str(venv_python), "-m", "pip", "install", "--quiet", "setproctitle"],
        check=True, capture_output=True,
    )
    return str(venv_python)

def _ensure_setproctitle() -> bool:
    try:
        import setproctitle              
        return True
    except ImportError:
        return False

def set_process_name(name: str) -> None:

    try:
        _ensure_setproctitle()
        import setproctitle
        setproctitle.setproctitle(name)
        return                                                            
    except Exception:
        pass

    try:
        lib = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
        lib.setprogname(name.encode("utf-8"))
    except Exception:
        pass

    try:
        argc = ctypes.c_int(0)
        argv = ctypes.POINTER(ctypes.c_char_p)()
        ctypes.pythonapi.Py_GetArgcArgv(ctypes.byref(argc), ctypes.byref(argv))
        if argc.value > 0 and argv[0]:
            buf      = name.encode("utf-8")
            orig_len = len(argv[0])
            padded   = buf[:orig_len].ljust(orig_len, b"\x00")
            ctypes.memmove(argv[0], padded, orig_len)
    except Exception:
        pass

class InstanceLock:

    def __init__(self, name: str):

        APP_SUPPORT.mkdir(parents=True, exist_ok=True)
        preferred = APP_SUPPORT / f"{name}.pid"
        try:
            preferred.touch()
            self._path = preferred
        except PermissionError:
            import tempfile
            self._path = Path(tempfile.gettempdir()) / f"hide_{name}.pid"
        self._fh = None

    def __enter__(self) -> "InstanceLock":
        self._fh = open(self._path, "w")
        try:
            if sys.platform == 'win32':
                import msvcrt
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self._fh.close()
            if exc.errno in (errno.EACCES, errno.EAGAIN):
                try:
                    pid = self._path.read_text().strip()
                    print(f"HIDE is already running (PID {pid}). Only one instance allowed.")
                except OSError:
                    print("HIDE is already running. Only one instance allowed.")
                sys.exit(0)
            raise

        self._fh.write(str(os.getpid()))
        self._fh.flush()
        return self

    def __exit__(self, *_) -> None:
        if self._fh:
            if sys.platform == 'win32':
                import msvcrt
                try:
                    msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            else:
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
            self._fh.close()
        self._path.unlink(missing_ok=True)
