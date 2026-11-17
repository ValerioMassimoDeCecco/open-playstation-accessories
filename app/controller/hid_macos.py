"""
macOS HID backend - IOKit (IOHIDManager) through ctypes.

No external dependency: it talks to the frameworks shipped with macOS
(IOKit.framework and CoreFoundation.framework), exactly like the Windows backend
talks to SetupAPI/hid.dll.

Highlights
----------
* Enumeration through IOHIDManager matching every HID device, filtered in Python
  by Sony vendor id (0x054C) and by the product ids we support.
* Input reports are delivered by an IOHIDDevice input-report callback running on
  a dedicated CFRunLoop thread. macOS strips the report id from the payload, so
  it is prepended again to keep the exact same byte layout used by the Windows
  backend (and therefore by the DualSense report parser).
* Output reports (lightbar, rumble, player LEDs) are sent with
  IOHIDDeviceSetReport, passing the report id separately as macOS expects.

NOTE: reading HID input on macOS >= 10.15 requires the "Input Monitoring"
permission for the application that launches Python (Terminal, iTerm, VS Code...).
"""

import ctypes
import os
import queue
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from .hid_base import SONY_VENDOR_ID, SUPPORTED_PRODUCTS

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

IOKIT_FRAMEWORK = "/System/Library/Frameworks/IOKit.framework/IOKit"
COREFOUNDATION_FRAMEWORK = (
    "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
)

kIOHIDOptionsTypeNone = 0
kIOHIDOptionsTypeSeizeDevice = 1
kIOReturnExclusiveAccess = 0xE00002EB
kIOHIDReportTypeInput = 0
kIOHIDReportTypeOutput = 1
kIOReturnSuccess = 0
kCFStringEncodingUTF8 = 0x08000100
kCFNumberSInt64Type = 4
kCFNumberSInt32Type = 3

MAX_REPORT_SIZE = 512
DEFAULT_INPUT_REPORT_LENGTH = 64
DEFAULT_OUTPUT_REPORT_LENGTH = 48

_IOHID_REPORT_CALLBACK = ctypes.CFUNCTYPE(
    None,               # return type
    ctypes.c_void_p,    # context
    ctypes.c_int32,     # IOReturn result
    ctypes.c_void_p,    # sender
    ctypes.c_int32,     # IOHIDReportType
    ctypes.c_uint32,    # reportID
    ctypes.POINTER(ctypes.c_uint8),  # report
    ctypes.c_long,      # reportLength (CFIndex)
)

# --------------------------------------------------------------------------- #
# Framework loading (lazy, thread safe, never raises on import)
# --------------------------------------------------------------------------- #

_frameworks: Optional[Tuple[Any, Any, Any]] = None
_load_error: Optional[str] = None
_load_lock = threading.Lock()

_STRING_KEYS: Dict[str, int] = {}
_int_cache_lock = threading.Lock()


def _string_key(name: str) -> int:
    """Creates (and caches) a CFStringRef from a Python string."""
    with _int_cache_lock:
        key = _STRING_KEYS.get(name)
        if key:
            return key
    cf = _load()[1]
    key = cf.CFStringCreateWithCString(
        None, name.encode("utf-8"), kCFStringEncodingUTF8
    )
    with _int_cache_lock:
        _STRING_KEYS[name] = key
    return key


def _load() -> Tuple[Any, Any]:
    """Loads and prototypes the IOKit / CoreFoundation entry points."""
    global _frameworks, _load_error

    if _frameworks is not None:
        return _frameworks

    with _load_lock:
        if _frameworks is not None:
            return _frameworks

        if sys.platform != "darwin":
            _load_error = "hid_macos richiede macOS (sistema rilevato: %s)" % sys.platform
            raise RuntimeError(_load_error)

        if not os.path.exists(IOKIT_FRAMEWORK):
            _load_error = "IOKit.framework non trovato"
            raise RuntimeError(_load_error)

        iokit = ctypes.CDLL(IOKIT_FRAMEWORK)
        cf = ctypes.CDLL(COREFOUNDATION_FRAMEWORK)

        # --- CoreFoundation ------------------------------------------------ #
        cf.CFStringCreateWithCString.restype = ctypes.c_void_p
        cf.CFStringCreateWithCString.argtypes = [
            ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32,
        ]
        cf.CFStringGetCString.restype = ctypes.c_bool
        cf.CFStringGetCString.argtypes = [
            ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32,
        ]
        cf.CFGetTypeID.restype = ctypes.c_ulong
        cf.CFGetTypeID.argtypes = [ctypes.c_void_p]
        cf.CFStringGetTypeID.restype = ctypes.c_ulong
        cf.CFNumberGetTypeID.restype = ctypes.c_ulong
        cf.CFNumberGetValue.restype = ctypes.c_bool
        cf.CFNumberGetValue.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p,
        ]
        cf.CFRetain.restype = ctypes.c_void_p
        cf.CFRetain.argtypes = [ctypes.c_void_p]
        cf.CFRelease.restype = None
        cf.CFRelease.argtypes = [ctypes.c_void_p]
        cf.CFSetGetCount.restype = ctypes.c_long
        cf.CFSetGetCount.argtypes = [ctypes.c_void_p]
        cf.CFSetGetValues.restype = None
        cf.CFSetGetValues.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
        ]
        cf.CFRunLoopGetCurrent.restype = ctypes.c_void_p
        cf.CFRunLoopGetMain.restype = ctypes.c_void_p
        cf.CFRunLoopRun.restype = None
        cf.CFRunLoopStop.restype = None
        cf.CFRunLoopStop.argtypes = [ctypes.c_void_p]
        cf.CFRunLoopRunInMode.restype = ctypes.c_int32
        cf.CFRunLoopRunInMode.argtypes = [
            ctypes.c_void_p, ctypes.c_double, ctypes.c_bool,
        ]

        # --- IOKit --------------------------------------------------------- #
        iokit.IOHIDManagerCreate.restype = ctypes.c_void_p
        iokit.IOHIDManagerCreate.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        iokit.IOHIDManagerSetDeviceMatching.restype = None
        iokit.IOHIDManagerSetDeviceMatching.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p,
        ]
        iokit.IOHIDManagerOpen.restype = ctypes.c_int32
        iokit.IOHIDManagerOpen.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        iokit.IOHIDManagerClose.restype = ctypes.c_int32
        iokit.IOHIDManagerClose.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        iokit.IOHIDManagerCopyDevices.restype = ctypes.c_void_p
        iokit.IOHIDManagerCopyDevices.argtypes = [ctypes.c_void_p]
        iokit.IOHIDManagerScheduleWithRunLoop.restype = None
        iokit.IOHIDManagerScheduleWithRunLoop.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
        ]
        iokit.IOHIDManagerUnscheduleFromRunLoop.restype = None
        iokit.IOHIDManagerUnscheduleFromRunLoop.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
        ]

        iokit.IOHIDDeviceGetProperty.restype = ctypes.c_void_p
        iokit.IOHIDDeviceGetProperty.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        iokit.IOHIDDeviceOpen.restype = ctypes.c_int32
        iokit.IOHIDDeviceOpen.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        iokit.IOHIDDeviceClose.restype = ctypes.c_int32
        iokit.IOHIDDeviceClose.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        iokit.IOHIDDeviceScheduleWithRunLoop.restype = None
        iokit.IOHIDDeviceScheduleWithRunLoop.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
        ]
        iokit.IOHIDDeviceUnscheduleFromRunLoop.restype = None
        iokit.IOHIDDeviceUnscheduleFromRunLoop.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
        ]
        iokit.IOHIDDeviceRegisterInputReportCallback.restype = None
        iokit.IOHIDDeviceRegisterInputReportCallback.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_long,
            _IOHID_REPORT_CALLBACK,
            ctypes.c_void_p,
        ]
        iokit.IOHIDDeviceSetReport.restype = ctypes.c_int32
        iokit.IOHIDDeviceSetReport.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_long,   # CFIndex reportID
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_long,   # CFIndex reportLength
        ]

        default_mode = ctypes.c_void_p.in_dll(cf, "kCFRunLoopDefaultMode")

        _frameworks = (iokit, cf, default_mode)
        return _frameworks


def last_error() -> str:
    return _load_error or ""


# --------------------------------------------------------------------------- #
# CoreFoundation helpers
# --------------------------------------------------------------------------- #

def _cf_string_to_py(value: Any) -> Optional[str]:
    if not value:
        return None
    _iokit, cf, _mode = _load()
    try:
        if cf.CFGetTypeID(value) != cf.CFStringGetTypeID():
            return None
        buf = ctypes.create_string_buffer(512)
        if cf.CFStringGetCString(value, buf, 511, kCFStringEncodingUTF8):
            return buf.value.decode("utf-8", "replace")
    except Exception:
        return None
    return None


def _cf_number_to_int(value: Any) -> Optional[int]:
    if not value:
        return None
    _iokit, cf, _mode = _load()
    try:
        if cf.CFGetTypeID(value) != cf.CFNumberGetTypeID():
            return None
        out = ctypes.c_int64()
        if cf.CFNumberGetValue(value, kCFNumberSInt64Type, ctypes.byref(out)):
            return int(out.value)
    except Exception:
        return None
    return None


def _property(device: Any, name: str) -> Any:
    iokit, _cf, _mode = _load()
    key = _string_key(name)
    if not key:
        return None
    return iokit.IOHIDDeviceGetProperty(device, key)


def _device_info(device: Any) -> Optional[Dict[str, Any]]:
    """Builds the public device dictionary for an IOHIDDeviceRef."""
    vid = _cf_number_to_int(_property(device, "VendorID"))
    pid = _cf_number_to_int(_property(device, "ProductID"))

    if vid is None or pid is None:
        return None
    if vid != SONY_VENDOR_ID:
        return None

    meta = SUPPORTED_PRODUCTS.get(pid)
    if meta is None:
        return None

    product = _cf_string_to_py(_property(device, "Product")) or meta["name"]
    transport = _cf_string_to_py(_property(device, "Transport")) or ""
    serial = (
        _cf_string_to_py(_property(device, "SerialNumber"))
        or _cf_string_to_py(_property(device, "USB Serial Number"))
        or ""
    )
    location = _cf_number_to_int(_property(device, "LocationID")) or 0
    usage_page = _cf_number_to_int(_property(device, "PrimaryUsagePage")) or 0
    usage = _cf_number_to_int(_property(device, "PrimaryUsage")) or 0

    is_bluetooth = transport.lower().startswith("bluetooth")

    path = "macos:%04X:%04X:%s:%08X:%02X:%02X" % (
        vid, pid, serial or ("loc%d" % location), location, usage_page, usage
    )

    return {
        "path": path,
        "vid": vid,
        "pid": pid,
        "name": product,
        "is_edge": bool(meta["is_edge"]),
        "is_bluetooth": is_bluetooth,
        "transport": transport or ("Bluetooth" if is_bluetooth else "USB"),
        "serial": serial,
        "usage_page": usage_page,
        "usage": usage,
        # Used only to pick the best interface first, never exposed to the API.
        "_rank": 0 if (usage_page == 0x01 and usage in (0x05, 0x04)) else 1,
        "_ref": device,
    }


# --------------------------------------------------------------------------- #
# Enumeration
# --------------------------------------------------------------------------- #

def _scan(retain: bool) -> List[Tuple[Any, Dict[str, Any]]]:
    """
    Returns [(device_ref, info_dict), ...].

    When ``retain`` is True every returned device_ref is CFRetain'ed and must be
    released by the caller with ``CFRelease``. When False the refs are borrowed
    from the device set and become invalid as soon as this function returns.
    """
    iokit, cf, mode = _load()

    manager = iokit.IOHIDManagerCreate(None, kIOHIDOptionsTypeNone)
    if not manager:
        return []

    run_loop = None
    devices_set = None
    results: List[Tuple[Any, Dict[str, Any]]] = []

    try:
        # NULL matching dictionary => every HID device is enumerated.
        iokit.IOHIDManagerSetDeviceMatching(manager, None)

        run_loop = cf.CFRunLoopGetCurrent()
        iokit.IOHIDManagerScheduleWithRunLoop(manager, run_loop, mode)
        iokit.IOHIDManagerOpen(manager, kIOHIDOptionsTypeNone)

        # Two short run-loop pumps let the manager populate its device set.
        cf.CFRunLoopRunInMode(mode, 0.02, True)
        cf.CFRunLoopRunInMode(mode, 0.02, True)

        devices_set = iokit.IOHIDManagerCopyDevices(manager)
        if not devices_set:
            return []

        count = int(cf.CFSetGetCount(devices_set))
        if count <= 0:
            return []

        array = (ctypes.c_void_p * count)()
        cf.CFSetGetValues(devices_set, array)

        seen: Dict[str, int] = {}
        for raw in array:
            ref = raw
            if not ref:
                continue
            try:
                info = _device_info(ref)
            except Exception:
                continue
            if not info:
                continue
            base_path = info["path"]
            # Make sure paths stay unique inside a single scan.
            if base_path in seen:
                seen[base_path] += 1
                info["path"] = "%s:%d" % (base_path, seen[base_path])
            else:
                seen[base_path] = 0
            if retain:
                cf.CFRetain(ref)
            results.append((ref, info))
    except Exception:
        return results
    finally:
        try:
            if devices_set:
                cf.CFRelease(devices_set)
            if run_loop:
                iokit.IOHIDManagerUnscheduleFromRunLoop(manager, run_loop, mode)
            iokit.IOHIDManagerClose(manager, kIOHIDOptionsTypeNone)
        except Exception:
            pass
        try:
            cf.CFRelease(manager)
        except Exception:
            pass

    # Gamepad interfaces first, then Bluetooth before USB is irrelevant here.
    results.sort(key=lambda item: (item[1].get("_rank", 1), item[1]["is_bluetooth"]))
    return results


def _open_device_ref(path: str) -> Optional[Any]:
    """Finds the IOHIDDeviceRef matching ``path`` and returns it retained."""
    iokit, cf, _mode = _load()
    scanned = _scan(retain=True)
    found = None
    for ref, info in scanned:
        if info["path"] == path and found is None:
            found = ref
            continue
        try:
            cf.CFRelease(ref)
        except Exception:
            pass
    return found


def enumerate_sony_devices() -> List[Dict[str, Any]]:
    """All connected Sony controllers, gamepad interface first."""
    devices: List[Dict[str, Any]] = []
    for _ref, info in _scan(retain=False):
        public = {k: v for k, v in info.items() if not k.startswith("_")}
        devices.append(public)
    return devices


# --------------------------------------------------------------------------- #
# Device object
# --------------------------------------------------------------------------- #

class HIDDevice:
    """An opened DualSense / DualSense Edge HID interface on macOS."""

    def __init__(self, path: str, vid: int, pid: int, name: str = ""):
        self.path = path
        self.vid = vid
        self.pid = pid
        self.name = name
        self.input_report_length = DEFAULT_INPUT_REPORT_LENGTH
        self.output_report_length = DEFAULT_OUTPUT_REPORT_LENGTH

        self._device: Optional[Any] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._run_loop: Optional[Any] = None
        self._started = threading.Event()
        self._reports: "queue.Queue[bytes]" = queue.Queue(maxsize=64)
        self._buffer = None
        self._callback = None
        self._lock = threading.RLock()
        self._write_errors = 0
        self._last_error = ""
        self._open_options = kIOHIDOptionsTypeNone

    # -- lifecycle ---------------------------------------------------------- #

    def open(self) -> bool:
        with self._lock:
            if self._device is not None:
                return True

            device = _open_device_ref(self.path)
            if not device:
                self._last_error = "Periferica macOS non trovata per il percorso %s" % self.path
                return False

            iokit, cf, _mode = _load()
            status = iokit.IOHIDDeviceOpen(device, kIOHIDOptionsTypeNone)
            options = kIOHIDOptionsTypeNone
            if (status & 0xFFFFFFFF) == kIOReturnExclusiveAccess:
                # The macOS game driver already owns the device exclusively.
                # Seizing it keeps the app usable (games will not see the pad
                # until this application is closed).
                status = iokit.IOHIDDeviceOpen(device, kIOHIDOptionsTypeSeizeDevice)
                if status == kIOReturnSuccess:
                    options = kIOHIDOptionsTypeSeizeDevice
                    print(
                        "[Hardware] Controller aperto in modalita esclusiva su macOS "
                        "(chiudi l'app per restituirlo ai giochi)."
                    )
            if status != kIOReturnSuccess:
                self._last_error = (
                    "IOHIDDeviceOpen ha restituito 0x%08X (permessi o driver in uso)"
                    % (status & 0xFFFFFFFF)
                )
                try:
                    cf.CFRelease(device)
                except Exception:
                    pass
                return False

            self._device = device
            self._open_options = options
            self._buffer = (ctypes.c_uint8 * MAX_REPORT_SIZE)()
            self._callback = _IOHID_REPORT_CALLBACK(self._on_report)
            self._running = True
            self._started.clear()

            self._thread = threading.Thread(
                target=self._run_loop_thread, name="macos-hid-runloop", daemon=True
            )
            self._thread.start()
            self._started.wait(timeout=1.0)
            return True

    def _run_loop_thread(self) -> None:
        iokit, cf, mode = _load()
        try:
            run_loop = cf.CFRunLoopGetCurrent()
            self._run_loop = run_loop
            iokit.IOHIDDeviceScheduleWithRunLoop(self._device, run_loop, mode)
            iokit.IOHIDDeviceRegisterInputReportCallback(
                self._device,
                self._buffer,
                len(self._buffer),
                self._callback,
                None,
            )
            self._started.set()
            cf.CFRunLoopRun()
            try:
                iokit.IOHIDDeviceUnscheduleFromRunLoop(self._device, run_loop, mode)
            except Exception:
                pass
        except Exception as exc:  # pragma: no cover - depends on host OS
            self._last_error = "RunLoop HID: %s" % exc
            self._started.set()

    def close(self) -> None:
        with self._lock:
            self._running = False
            run_loop = self._run_loop
            thread = self._thread
            device = self._device
            options = self._open_options
            self._device = None
            self._thread = None
            self._run_loop = None

        if run_loop:
            try:
                _iokit, cf, _mode = _load()
                cf.CFRunLoopStop(run_loop)
            except Exception:
                pass
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=0.6)

        if device:
            try:
                iokit, cf, _mode = _load()
                iokit.IOHIDDeviceClose(device, options)
            except Exception:
                pass
            try:
                _iokit, cf, _mode = _load()
                cf.CFRelease(device)
            except Exception:
                pass

        self._callback = None
        self._buffer = None

        # Drain pending reports so a new connection starts clean.
        try:
            while True:
                self._reports.get_nowait()
        except queue.Empty:
            pass

    # -- input -------------------------------------------------------------- #

    def _on_report(self, _context, result, _sender, _rtype, report_id, report, length):
        if result != kIOReturnSuccess or not length:
            return
        try:
            payload = bytes(bytearray(report[i] for i in range(int(length))))
        except Exception:
            return
        packet = bytes([int(report_id) & 0xFF]) + payload
        try:
            self._reports.put_nowait(packet)
        except queue.Full:
            try:
                self._reports.get_nowait()
                self._reports.put_nowait(packet)
            except Exception:
                pass

    def read_input_report(self) -> Optional[bytes]:
        try:
            return self._reports.get(timeout=0.1)
        except queue.Empty:
            return None

    def wait_for_first_report(self, timeout: float = 2.0) -> bool:
        """Blocks until the first hardware report arrives (or times out)."""
        deadline = time.time() + max(0.1, float(timeout))
        while time.time() < deadline and self._running:
            try:
                packet = self._reports.get(timeout=0.1)
            except queue.Empty:
                continue
            if packet:
                try:
                    self._reports.put_nowait(packet)
                except Exception:
                    pass
                return True
        return False

    # -- output ------------------------------------------------------------- #

    def write_output_report(self, data: bytes) -> bool:
        if not data or self._device is None:
            return False

        iokit, _cf, _mode = _load()
        report_id = int(data[0]) & 0xFF
        payload = bytes(data[1:])
        if not payload:
            return False

        buf = (ctypes.c_uint8 * len(payload)).from_buffer_copy(payload)
        status = iokit.IOHIDDeviceSetReport(
            self._device, kIOHIDReportTypeOutput, report_id, buf, len(payload)
        )
        if status != kIOReturnSuccess:
            self._write_errors += 1
            self._last_error = "IOHIDDeviceSetReport 0x%08X" % (status & 0xFFFFFFFF)
            return False
        return True

    # -- diagnostics -------------------------------------------------------- #

    def last_error(self) -> str:
        return self._last_error
