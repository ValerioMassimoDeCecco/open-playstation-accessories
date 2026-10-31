"""
Native Windows HID communication wrapper via ctypes (no external C library required).
Explicit 64-bit types for setupapi.dll, hid.dll, and kernel32.dll.
"""

import ctypes
from ctypes import wintypes
import sys
import threading
import time
from typing import List, Optional, Tuple, Dict, Any

# Windows API constants
DIGCF_PRESENT = 0x00000002
DIGCF_DEVICEINTERFACE = 0x00000010
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value

class GUID(ctypes.Structure):
    _fields_ = [
        ('Data1', wintypes.DWORD),
        ('Data2', wintypes.WORD),
        ('Data3', wintypes.WORD),
        ('Data4', wintypes.BYTE * 8)
    ]

class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [
        ('cbSize', wintypes.DWORD),
        ('InterfaceClassGuid', GUID),
        ('Flags', wintypes.DWORD),
        ('Reserved', ctypes.c_size_t)
    ]

class HIDP_CAPS(ctypes.Structure):
    _fields_ = [
        ('Usage', wintypes.USHORT),
        ('UsagePage', wintypes.USHORT),
        ('InputReportByteLength', wintypes.USHORT),
        ('OutputReportByteLength', wintypes.USHORT),
        ('FeatureReportByteLength', wintypes.USHORT),
        ('Reserved', wintypes.USHORT * 17),
        ('NumberLinkCollectionNodes', wintypes.USHORT),
        ('NumberInputButtonCaps', wintypes.USHORT),
        ('NumberInputValueCaps', wintypes.USHORT),
        ('NumberInputDataIndices', wintypes.USHORT),
        ('NumberOutputButtonCaps', wintypes.USHORT),
        ('NumberOutputValueCaps', wintypes.USHORT),
        ('NumberOutputDataIndices', wintypes.USHORT),
        ('NumberFeatureButtonCaps', wintypes.USHORT),
        ('NumberFeatureValueCaps', wintypes.USHORT),
        ('NumberFeatureDataIndices', wintypes.USHORT),
    ]

# Setup explicit 64-bit Windows API signatures
setupapi = ctypes.windll.setupapi
setupapi.SetupDiGetClassDevsW.restype = ctypes.c_void_p
setupapi.SetupDiGetClassDevsW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, wintypes.HWND, wintypes.DWORD]

setupapi.SetupDiEnumDeviceInterfaces.restype = wintypes.BOOL
setupapi.SetupDiEnumDeviceInterfaces.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p]

setupapi.SetupDiGetDeviceInterfaceDetailW.restype = wintypes.BOOL
setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p]

setupapi.SetupDiDestroyDeviceInfoList.restype = wintypes.BOOL
setupapi.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]

kernel32 = ctypes.windll.kernel32
kernel32.CreateFileW.restype = wintypes.HANDLE
kernel32.CreateFileW.argtypes = [
    wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
    wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE
]

kernel32.ReadFile.restype = wintypes.BOOL
kernel32.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]

kernel32.WriteFile.restype = wintypes.BOOL
kernel32.WriteFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]

kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]


def get_hid_caps(handle: wintypes.HANDLE) -> Optional[Tuple[int, int, int, int]]:
    """Returns (input_len, output_len, usage, usage_page) for an open HID handle."""
    preparsed = ctypes.c_void_p()
    if not ctypes.windll.hid.HidD_GetPreparsedData(handle, ctypes.byref(preparsed)):
        return None

    caps = HIDP_CAPS()
    status = ctypes.windll.hid.HidP_GetCaps(preparsed, ctypes.byref(caps))
    ctypes.windll.hid.HidD_FreePreparsedData(preparsed)

    if status == 0x00110000:  # HIDP_STATUS_SUCCESS
        return (
            int(caps.InputReportByteLength),
            int(caps.OutputReportByteLength),
            int(caps.Usage),
            int(caps.UsagePage)
        )
    return None


class WindowsHIDDevice:
    """Represents an opened physical Windows HID device."""

    def __init__(self, path: str, vid: int, pid: int, name: str = ""):
        self.path = path
        self.vid = vid
        self.pid = pid
        self.name = name
        self.handle = None
        self.input_report_length = 64
        self.output_report_length = 48
        self._is_open = False
        self._lock = threading.Lock()

    def open(self) -> bool:
        with self._lock:
            if self._is_open:
                return True

            self.handle = kernel32.CreateFileW(
                self.path,
                GENERIC_READ | GENERIC_WRITE,
                FILE_SHARE_READ | FILE_SHARE_WRITE,
                None,
                OPEN_EXISTING,
                0,
                None
            )

            if self.handle in (INVALID_HANDLE_VALUE, 0, -1, 0xFFFFFFFFFFFFFFFF, 0xFFFFFFFF):
                # Fallback to read-only if shared write is claimed
                self.handle = kernel32.CreateFileW(
                    self.path,
                    GENERIC_READ,
                    FILE_SHARE_READ | FILE_SHARE_WRITE,
                    None,
                    OPEN_EXISTING,
                    0,
                    None
                )

            if self.handle in (INVALID_HANDLE_VALUE, 0, -1, 0xFFFFFFFFFFFFFFFF, 0xFFFFFFFF):
                self.handle = None
                return False

            caps = get_hid_caps(self.handle)
            if caps:
                self.input_report_length = caps[0] if caps[0] > 0 else 64
                self.output_report_length = caps[1] if caps[1] > 0 else 48

            self._is_open = True
            return True

    def close(self):
        with self._lock:
            if self.handle and self.handle not in (INVALID_HANDLE_VALUE, 0, -1, 0xFFFFFFFFFFFFFFFF, 0xFFFFFFFF):
                kernel32.CloseHandle(self.handle)
            self.handle = None
            self._is_open = False

    def read_input_report(self) -> Optional[bytes]:
        """Reads a real physical input report synchronously."""
        if not self._is_open or not self.handle:
            return None

        size = self.input_report_length
        buf = ctypes.create_string_buffer(size)
        bytes_read = wintypes.DWORD()

        ok = kernel32.ReadFile(
            self.handle,
            buf,
            size,
            ctypes.byref(bytes_read),
            None
        )

        if ok and bytes_read.value > 0:
            return buf.raw[:bytes_read.value]
        return None

    def write_output_report(self, data: bytes) -> bool:
        """Sends an output report to the physical controller."""
        if not self._is_open or not self.handle:
            return False

        # DualSense reports: 48 bytes (USB 0x02) or 78 bytes (BT 0x31)
        # Never pad BT 78-byte reports to Windows descriptor lengths like 547!
        buf = (ctypes.c_char * len(data)).from_buffer_copy(data)
        bytes_written = wintypes.DWORD()

        ok = kernel32.WriteFile(
            self.handle,
            buf,
            len(data),
            ctypes.byref(bytes_written),
            None
        )

        if not ok:
            ok = ctypes.windll.hid.HidD_SetOutputReport(
                self.handle,
                buf,
                len(data)
            )

        return bool(ok)


def enumerate_sony_devices() -> List[Dict[str, Any]]:
    """
    Enumerate all connected real physical Sony DualSense / DualSense Edge controllers.
    Sony VID: 0x054C
    DualSense PID: 0x0CE6
    DualSense Edge PID: 0x0DF2
    """
    hid_guid = GUID()
    ctypes.windll.hid.HidD_GetHidGuid(ctypes.byref(hid_guid))

    hdev = setupapi.SetupDiGetClassDevsW(
        ctypes.byref(hid_guid), None, None, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE
    )

    if not hdev or hdev in (-1, 0xFFFFFFFFFFFFFFFF):
        return []

    did = SP_DEVICE_INTERFACE_DATA()
    did.cbSize = ctypes.sizeof(SP_DEVICE_INTERFACE_DATA)

    devices = []
    index = 0

    while setupapi.SetupDiEnumDeviceInterfaces(
        hdev, None, ctypes.byref(hid_guid), index, ctypes.byref(did)
    ):
        req_size = wintypes.DWORD()
        setupapi.SetupDiGetDeviceInterfaceDetailW(
            hdev, ctypes.byref(did), None, 0, ctypes.byref(req_size), None
        )

        buf = ctypes.create_string_buffer(req_size.value)
        # cbSize on 64-bit must be 8
        ctypes.cast(ctypes.byref(buf), ctypes.POINTER(wintypes.DWORD))[0] = 8

        if setupapi.SetupDiGetDeviceInterfaceDetailW(
            hdev, ctypes.byref(did), ctypes.byref(buf), req_size.value, None, None
        ):
            device_path = ctypes.wstring_at(ctypes.addressof(buf) + 4)
            lower_path = device_path.lower()

            # Matches both USB ('vid_054c') and Bluetooth ('vid&0002054c' or '054c')
            if "054c" in lower_path:
                pid = 0
                vid = 0x054C
                model_name = "PlayStation Controller"
                is_edge = False

                if "0ce6" in lower_path:
                    pid = 0x0CE6
                    model_name = "DualSense Wireless Controller"
                elif "0df2" in lower_path:
                    pid = 0x0DF2
                    model_name = "DualSense Edge Wireless Controller"
                    is_edge = True
                elif "05c4" in lower_path:
                    pid = 0x05C4
                    model_name = "DualShock 4 Wireless Controller (Gen 1)"
                elif "09cc" in lower_path:
                    pid = 0x09CC
                    model_name = "DualShock 4 Wireless Controller (Gen 2)"
                else:
                    index += 1
                    continue

                is_bluetooth = ("00001124" in lower_path) or ("bthenum" in lower_path)

                devices.append({
                    "path": device_path,
                    "vid": vid,
                    "pid": pid,
                    "name": model_name,
                    "is_edge": is_edge,
                    "is_bluetooth": is_bluetooth
                })

        index += 1

    setupapi.SetupDiDestroyDeviceInfoList(hdev)

    # Sort devices so USB is prioritized over Bluetooth if both are active
    devices.sort(key=lambda d: 1 if d["is_bluetooth"] else 0)
    return devices
