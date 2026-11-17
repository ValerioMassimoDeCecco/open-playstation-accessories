"""
macOS backend tests.

IOKit cannot be loaded on Linux/Windows, so the frameworks are replaced by small
test doubles that mimic the exact ctypes surface used by hid_macos.py. This
validates the enumeration/filtering logic, the device handshake and the report
callback (including the report-id prepending) on every platform.

The real framework bindings are only exercised on a real Mac; these tests make
sure the pure-python logic around them is correct.
"""

import ctypes
import os
import sys
import threading
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from app.controller import hid_macos


class FakeCF:
    """Minimal CoreFoundation double."""

    STRING_TYPE = 101
    NUMBER_TYPE = 202

    def __init__(self):
        self._objects = {}
        self._next = 500
        self._lock = threading.Lock()
        self.retain_count = 0
        self.release_count = 0
        self.run_loop_stopped = threading.Event()

    # -- construction ------------------------------------------------------- #
    def new_string(self, text):
        with self._lock:
            ref = self._next
            self._next += 1
            self._objects[ref] = ("string", text)
        return ref

    def new_number(self, value):
        with self._lock:
            ref = self._next
            self._next += 1
            self._objects[ref] = ("number", int(value))
        return ref

    def value_of(self, ref, kind):
        entry = self._objects.get(ref)
        if not entry or entry[0] != kind:
            return None
        return entry[1]

    # -- CF API ------------------------------------------------------------- #
    def CFStringCreateWithCString(self, _alloc, c_string, _encoding):
        return self.new_string(c_string.decode("utf-8"))

    def CFStringGetCString(self, ref, buffer, _size, _encoding):
        value = self.value_of(ref, "string")
        if value is None:
            return False
        encoded = value.encode("utf-8")
        buffer.value = encoded
        return True

    def CFGetTypeID(self, ref):
        entry = self._objects.get(ref)
        if not entry:
            return 0
        return self.STRING_TYPE if entry[0] == "string" else self.NUMBER_TYPE

    def CFStringGetTypeID(self):
        return self.STRING_TYPE

    def CFNumberGetTypeID(self):
        return self.NUMBER_TYPE

    def CFNumberGetValue(self, ref, _type, out_pointer):
        value = self.value_of(ref, "number")
        if value is None:
            return False
        ctypes.cast(out_pointer, ctypes.POINTER(ctypes.c_int64))[0] = value
        return True

    def CFRetain(self, _ref):
        self.retain_count += 1
        return _ref

    def CFRelease(self, _ref):
        self.release_count += 1

    def CFSetGetCount(self, ref):
        entry = self._objects.get(ref)
        if entry and entry[0] == "set":
            return len(entry[1])
        return 0

    def CFSetGetValues(self, ref, values):
        entry = self._objects.get(ref)
        if not entry or entry[0] != "set":
            return
        for index, device_ref in enumerate(entry[1]):
            values[index] = device_ref

    def CFRunLoopGetCurrent(self):
        return 1

    def CFRunLoopGetMain(self):
        return 1

    def CFRunLoopRun(self):
        self.run_loop_stopped.wait(5)

    def CFRunLoopStop(self, _run_loop):
        self.run_loop_stopped.set()

    def CFRunLoopRunInMode(self, _mode, _seconds, _return_after_source):
        return 0


class FakeDevice:
    def __init__(self, cf, properties):
        self.cf = cf
        self.properties = {
            key: (cf.new_string(value) if isinstance(value, str) else cf.new_number(value))
            for key, value in properties.items()
        }
        self.opened_with = None
        self.closed_with = None
        self.report_callback = None
        self.report_buffer = None

    def open_status(self, options):
        self.opened_with = options
        return 0


class FakeIOKit:
    def __init__(self, cf, devices):
        self.cf = cf
        self.devices = devices
        # IOKit hands out opaque integer refs (mach ports): mimic that.
        self.by_ref = {
            1000 + index: device for index, (device, _meta) in enumerate(devices)
        }
        self.callback_buffer = None
        self.callback_size = None

    def IOHIDManagerCreate(self, _alloc, _options):
        return 900

    def IOHIDManagerSetDeviceMatching(self, _manager, _matching):
        return None

    def IOHIDManagerOpen(self, _manager, _options):
        return 0

    def IOHIDManagerClose(self, _manager, _options):
        return 0

    def IOHIDManagerScheduleWithRunLoop(self, _manager, _loop, _mode):
        return None

    def IOHIDManagerUnscheduleFromRunLoop(self, _manager, _loop, _mode):
        return None

    def IOHIDManagerCopyDevices(self, _manager):
        ref = 901
        self.cf._objects[ref] = ("set", list(self.by_ref.keys()))
        return ref

    def IOHIDDeviceGetProperty(self, device_ref, key_ref):
        name = self.cf.value_of(key_ref, "string")
        return self.by_ref[device_ref].properties.get(name)

    def IOHIDDeviceOpen(self, device_ref, options):
        return self.by_ref[device_ref].open_status(options)

    def IOHIDDeviceClose(self, device_ref, options):
        self.by_ref[device_ref].closed_with = options
        return 0

    def IOHIDDeviceScheduleWithRunLoop(self, _device, _loop, _mode):
        return None

    def IOHIDDeviceUnscheduleFromRunLoop(self, _device, _loop, _mode):
        return None

    def IOHIDDeviceRegisterInputReportCallback(
        self, device_ref, buffer, size, callback, _context
    ):
        device = self.by_ref[device_ref]
        device.report_callback = callback
        device.report_buffer = buffer
        self.callback_buffer = buffer
        self.callback_size = size
        return None

    def IOHIDDeviceSetReport(self, _device, _type, _report_id, _buffer, _length):
        return 0


class MacOSBackendTests(unittest.TestCase):
    def setUp(self):
        self.cf = FakeCF()
        self.default_mode = 1234
        self.dualsense = FakeDevice(self.cf, {
            "VendorID": 0x054C,
            "ProductID": 0x0CE6,
            "Product": "DualSense Wireless Controller",
            "Transport": "USB",
            "SerialNumber": "ABC123",
            "LocationID": 0x01100000,
            "PrimaryUsagePage": 0x01,
            "PrimaryUsage": 0x05,
        })
        self.edge = FakeDevice(self.cf, {
            "VendorID": 0x054C,
            "ProductID": 0x0DF2,
            "Product": "DualSense Edge Wireless Controller",
            "Transport": "Bluetooth",
            "LocationID": 0x0,
            "PrimaryUsagePage": 0x01,
            "PrimaryUsage": 0x05,
        })
        self.keyboard = FakeDevice(self.cf, {
            "VendorID": 0x05AC,
            "ProductID": 0x0250,
            "Product": "Apple Keyboard",
            "Transport": "USB",
            "PrimaryUsagePage": 0x01,
            "PrimaryUsage": 0x06,
        })
        self.iokit = FakeIOKit(
            self.cf, [(self.dualsense, {}), (self.edge, {}), (self.keyboard, {})]
        )

        self._previous = hid_macos._frameworks
        hid_macos._frameworks = (self.iokit, self.cf, self.default_mode)
        hid_macos._STRING_KEYS.clear()
        self.addCleanup(self._restore_frameworks)

    def _restore_frameworks(self):
        hid_macos._frameworks = self._previous
        hid_macos._STRING_KEYS.clear()

    def test_enumeration_filters_sony_devices(self):
        devices = hid_macos.enumerate_sony_devices()
        self.assertEqual(len(devices), 2)
        pids = sorted(device["pid"] for device in devices)
        self.assertEqual(pids, [0x0CE6, 0x0DF2])
        for device in devices:
            self.assertTrue(device["path"].startswith("macos:"))
            self.assertNotIn("_ref", device)
            self.assertNotIn("_rank", device)

    def test_edge_is_flagged_and_bluetooth_detected(self):
        devices = {device["pid"]: device for device in hid_macos.enumerate_sony_devices()}
        self.assertTrue(devices[0x0DF2]["is_edge"])
        self.assertTrue(devices[0x0DF2]["is_bluetooth"])
        self.assertFalse(devices[0x0CE6]["is_edge"])
        self.assertFalse(devices[0x0CE6]["is_bluetooth"])

    def test_open_close_and_report_callback(self):
        info = hid_macos.enumerate_sony_devices()[0]
        device = hid_macos.HIDDevice(info["path"], info["vid"], info["pid"], info["name"])

        self.assertTrue(device.open())
        self.assertIsNotNone(self.dualsense.report_callback)

        payload = bytes([0x80, 0x81, 0x82, 0x83] + [0] * 60)
        raw = (ctypes.c_uint8 * len(payload)).from_buffer_copy(payload)
        self.dualsense.report_callback(
            None, 0, None, hid_macos.kIOHIDReportTypeInput, 0x01, raw, len(payload)
        )

        packet = device.read_input_report()
        self.assertIsNotNone(packet)
        self.assertEqual(packet[0], 0x01)          # report id prepended again
        self.assertEqual(packet[1:5], payload[:4])
        self.assertEqual(len(packet), len(payload) + 1)

        self.assertTrue(device.write_output_report(bytes(48)))
        device.close()
        self.assertIsNotNone(self.dualsense.closed_with)

    def test_unknown_path_cannot_be_opened(self):
        device = hid_macos.HIDDevice("macos:dead:beef", 0x054C, 0x0CE6, "Ghost")
        self.assertFalse(device.open())
        self.assertIn("non trovata", device.last_error())

    def test_scan_releases_copied_objects(self):
        before = self.cf.release_count
        hid_macos.enumerate_sony_devices()
        self.assertGreater(self.cf.release_count, before)


if __name__ == "__main__":
    unittest.main()
