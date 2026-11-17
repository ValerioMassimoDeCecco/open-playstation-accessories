"""
Linux HID backend - hidraw nodes, standard library only.

Linux exposes every HID interface as /dev/hidrawN; the matching metadata lives in
/sys/class/hidraw/hidrawN/device/uevent. Reports are read/written with plain
os.read / os.write calls (the buffer always carries the report id as first byte,
exactly like the Windows backend).
"""

import errno
import os
import select
import threading
from typing import Any, Dict, List, Optional

from .hid_base import SONY_VENDOR_ID, SUPPORTED_PRODUCTS

HIDRAW_CLASS = "/sys/class/hidraw"
DEFAULT_INPUT_REPORT_LENGTH = 64
DEFAULT_OUTPUT_REPORT_LENGTH = 48


def _read_uevent(name: str) -> Dict[str, str]:
    path = os.path.join(HIDRAW_CLASS, name, "device", "uevent")
    data: Dict[str, str] = {}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                data[key] = value
    except OSError:
        return {}
    return data


def _parse_hid_id(raw: str) -> Optional[tuple]:
    parts = (raw or "").split(":")
    if len(parts) != 3:
        return None
    try:
        return int(parts[0], 16), int(parts[1], 16), int(parts[2], 16)
    except ValueError:
        return None


def enumerate_sony_devices() -> List[Dict[str, Any]]:
    """All connected Sony controllers exposed through hidraw."""
    if not os.path.isdir(HIDRAW_CLASS):
        return []

    devices: List[Dict[str, Any]] = []
    try:
        entries = sorted(os.listdir(HIDRAW_CLASS))
    except OSError:
        return []

    for entry in entries:
        if not entry.startswith("hidraw"):
            continue
        uevent = _read_uevent(entry)
        ids = _parse_hid_id(uevent.get("HID_ID", ""))
        if not ids:
            continue
        _bus, vid, pid = ids
        if vid != SONY_VENDOR_ID:
            continue
        meta = SUPPORTED_PRODUCTS.get(pid)
        if not meta:
            continue

        name = uevent.get("HID_NAME", meta["name"]) or meta["name"]
        uniq = (uevent.get("HID_UNIQ") or "").strip()
        is_bluetooth = bool(uniq) and not uniq.startswith("0000")

        devices.append({
            "path": os.path.join("/dev", entry),
            "vid": vid,
            "pid": pid,
            "name": name,
            "is_edge": bool(meta["is_edge"]),
            "is_bluetooth": is_bluetooth,
            "serial": uniq,
        })

    devices.sort(key=lambda device: 1 if device["is_bluetooth"] else 0)
    return devices


class HIDDevice:
    """A DualSense HID interface opened through /dev/hidrawN."""

    def __init__(self, path: str, vid: int, pid: int, name: str = ""):
        self.path = path
        self.vid = vid
        self.pid = pid
        self.name = name
        self.input_report_length = DEFAULT_INPUT_REPORT_LENGTH
        self.output_report_length = DEFAULT_OUTPUT_REPORT_LENGTH
        self._fd: Optional[int] = None
        self._lock = threading.RLock()
        self._last_error = ""

    def open(self) -> bool:
        with self._lock:
            if self._fd is not None:
                return True
            for flags in (os.O_RDWR | os.O_NONBLOCK, os.O_RDONLY | os.O_NONBLOCK):
                try:
                    self._fd = os.open(self.path, flags)
                    return True
                except OSError as exc:
                    self._last_error = str(exc)
            return False

    def close(self) -> None:
        with self._lock:
            if self._fd is not None:
                try:
                    os.close(self._fd)
                except OSError:
                    pass
            self._fd = None

    def read_input_report(self) -> Optional[bytes]:
        fd = self._fd
        if fd is None:
            return None
        try:
            ready, _, _ = select.select([fd], [], [], 0.1)
        except (OSError, ValueError):
            return None
        if not ready:
            return None
        try:
            chunk = os.read(fd, 512)
        except BlockingIOError:
            return None
        except OSError as exc:
            if exc.errno not in (errno.EAGAIN, errno.EINTR):
                self._last_error = str(exc)
            return None
        return chunk or None

    def write_output_report(self, data: bytes) -> bool:
        fd = self._fd
        if fd is None or not data:
            return False
        try:
            written = os.write(fd, bytes(data))
            return written == len(data)
        except OSError as exc:
            self._last_error = str(exc)
            return False

    def wait_for_first_report(self, timeout: float = 2.0) -> bool:
        return True

    def last_error(self) -> str:
        return self._last_error
