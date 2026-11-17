"""
Cross-platform HID layer selector.

Every operating system gets its own zero-dependency backend (pure Python + ctypes /
stdlib), selected at runtime:

    Windows  ->  app.controller.hid_windows   (SetupAPI.dll / hid.dll)
    macOS    ->  app.controller.hid_macos     (IOKit.framework / IOHIDManager)
    Linux    ->  app.controller.hid_linux     (hidraw nodes in /sys/class/hidraw)

Importing this module never fails on an unsupported system: in that case a Null
backend is returned so that the web interface still starts (it will simply report
"nessun controller collegato" instead of crashing).
"""

import importlib
import platform as _platform
import sys
import threading
from typing import Any, Dict, List, Optional

# Sony vendor id and the product ids this application knows about.
SONY_VENDOR_ID = 0x054C

SUPPORTED_PRODUCTS: Dict[int, Dict[str, Any]] = {
    0x0CE6: {"name": "DualSense Wireless Controller", "is_edge": False},
    0x0DF2: {"name": "DualSense Edge Wireless Controller", "is_edge": True},
    0x05C4: {"name": "DualShock 4 Wireless Controller (Gen 1)", "is_edge": False},
    0x09CC: {"name": "DualShock 4 Wireless Controller (Gen 2)", "is_edge": False},
}

_OS_LABELS = {
    "win32": "Windows",
    "cygwin": "Windows",
    "darwin": "macOS",
    "linux": "Linux",
}

_BACKEND_MODULES = {
    "win32": ("app.controller.hid_windows", "Windows SetupAPI / HID class (ctypes)"),
    "cygwin": ("app.controller.hid_windows", "Windows SetupAPI / HID class (ctypes)"),
    "darwin": ("app.controller.hid_macos", "macOS IOKit / IOHIDManager (ctypes)"),
    "linux": ("app.controller.hid_linux", "Linux hidraw (/dev/hidraw*)"),
}

HINTS = {
    "darwin": (
        "Se il controller e collegato ma non viene rilevato, concedi il permesso "
        "'Monitoraggio input' al Terminale in Impostazioni di Sistema > Privacy e Sicurezza."
    ),
    "win32": "Verifica il cavo USB o ri-associa il controller via Bluetooth.",
    "linux": (
        "Su Linux servono i permessi sui nodi /dev/hidraw* (regola udev o gruppo input)."
    ),
}

_backend_lock = threading.Lock()
_backend_module: Any = None
_backend_loaded = False
_backend_error: Optional[str] = None


def platform_key() -> str:
    """Returns the normalized platform key: 'win32', 'darwin' or 'linux'."""
    if sys.platform.startswith("win"):
        return "win32"
    if sys.platform == "darwin":
        return "darwin"
    if sys.platform.startswith("linux"):
        return "linux"
    return sys.platform


def os_label() -> str:
    key = platform_key()
    if key in _OS_LABELS:
        return _OS_LABELS[key]
    return _platform.system() or key


def is_supported() -> bool:
    return platform_key() in _BACKEND_MODULES


def backend_label() -> str:
    entry = _BACKEND_MODULES.get(platform_key())
    if entry:
        return entry[1]
    return "Nessun backend HID disponibile"


def get_platform_info() -> Dict[str, Any]:
    """Small JSON-serializable description of the active platform/backend."""
    key = platform_key()
    return {
        "os": os_label(),
        "platform": key,
        "backend": backend_label(),
        "supported": is_supported(),
        "hint": HINTS.get(key, ""),
        "error": _backend_error or "",
    }


def _load_backend() -> Any:
    """Imports (once) the HID backend module for the current operating system."""
    global _backend_module, _backend_loaded, _backend_error

    with _backend_lock:
        if _backend_loaded:
            return _backend_module

        _backend_loaded = True
        entry = _BACKEND_MODULES.get(platform_key())
        if not entry:
            _backend_error = (
                "Sistema operativo non supportato: %s" % _platform.system()
            )
            _backend_module = None
            return None

        module_name = entry[0]
        try:
            _backend_module = importlib.import_module(module_name)
        except Exception as exc:  # pragma: no cover - depends on host OS
            _backend_module = None
            _backend_error = "Backend %s non disponibile: %s" % (module_name, exc)
        return _backend_module


class NullHIDDevice:
    """Fallback device used when no native backend is available.

    It behaves like a permanently disconnected controller, so the rest of the
    application keeps working instead of raising exceptions.
    """

    def __init__(self, path: str = "", vid: int = 0, pid: int = 0, name: str = ""):
        self.path = path
        self.vid = vid
        self.pid = pid
        self.name = name
        self.input_report_length = 64
        self.output_report_length = 48

    def open(self) -> bool:
        return False

    def close(self) -> None:
        return None

    def read_input_report(self) -> Optional[bytes]:
        return None

    def write_output_report(self, data: bytes) -> bool:
        return False


def enumerate_sony_devices() -> List[Dict[str, Any]]:
    """Returns the list of connected Sony controllers (empty list on any failure)."""
    backend = _load_backend()
    if backend is None:
        return []
    try:
        devices = backend.enumerate_sony_devices()
    except Exception as exc:  # pragma: no cover - defensive
        global _backend_error
        _backend_error = "Errore enumerazione HID: %s" % exc
        return []
    return devices or []


def create_hid_device(path: str, vid: int, pid: int, name: str = ""):
    """Builds the platform specific HID device object (never raises)."""
    backend = _load_backend()
    if backend is None:
        return NullHIDDevice(path, vid, pid, name)
    try:
        return backend.HIDDevice(path, vid, pid, name)
    except Exception as exc:  # pragma: no cover - defensive
        global _backend_error
        _backend_error = "Impossibile creare il device HID: %s" % exc
        return NullHIDDevice(path, vid, pid, name)


__all__ = [
    "SONY_VENDOR_ID",
    "SUPPORTED_PRODUCTS",
    "NullHIDDevice",
    "backend_label",
    "create_hid_device",
    "enumerate_sony_devices",
    "get_platform_info",
    "is_supported",
    "os_label",
    "platform_key",
]
