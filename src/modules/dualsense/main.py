import logging
import struct
import threading
import time
import zlib

import hid

from .triggers import M_RIGID, off

log = logging.getLogger("fh5ds.dualsense")

VENDOR_ID = 0x054C
PRODUCT_IDS = (0x0CE6, 0x0DF2)  # DualSense, DualSense Edge

# valid_flag0: 0x01 (R motor), 0x02 (L motor), 0x04 (R trigger), 0x08 (L trigger).
# Some firmware needs motor bits set for trigger bits to be processed.
TRIG_FLAGS = 0x01 | 0x02 | 0x04 | 0x08

USB = {"rid": 0x02, "flags": 1, "r": 11, "l": 22, "size": 64, "bt": False}
BT  = {"rid": 0x31, "flags": 2, "r": 12, "l": 23, "size": 78, "bt": True}


def _find_gamepad():
    """Pick the Game Pad HID interface (usage_page=1, usage=5).
    Audio/sensor interfaces share VID/PID and silently drop trigger writes."""
    devices = hid.enumerate(VENDOR_ID, 0)
    for d in devices:
        if (d.get("product_id") in PRODUCT_IDS
                and d.get("usage_page", 1) == 1
                and d.get("usage", 5) == 5):
            return d
    
    # Fallback: if usage info is missing (some systems/drivers), pick first matching VID/PID
    for d in devices:
        if d.get("product_id") in PRODUCT_IDS:
            log.warning("Usage page/usage not found, picking first matching VID/PID: %s", d.get("path"))
            return d

    raise RuntimeError("DualSense gamepad not found.")


def _is_bluetooth(info):
    bus_type = info.get("bus_type")
    if bus_type is not None:
        return bus_type == 2
    path = info.get("path", b"")
    if isinstance(path, str):
        path = path.encode()
    return b"BTHENUM" in path.upper()


class DualSense:
    """Triggers-only DualSense writer. Steam keeps rumble bits untouched."""

    def __init__(self, startup_pulse_force: int = 180, enable_startup_pulse: bool = True):
        self.dev = None
        self.lay = USB
        self._lock = threading.Lock()
        self._left = self._right = off()
        self._dirty = False
        self._running = False
        self._thread = None
        self._pulse_force = startup_pulse_force
        self._enable_startup_pulse = enable_startup_pulse

    def open(self):
        info = _find_gamepad()
        self.dev = hid.device()
        self.dev.open_path(info["path"])
        self.lay = BT if _is_bluetooth(info) else USB
        self.dev.set_nonblocking(True)
        log.info("DualSense connected (%s)", "BT" if self.lay["bt"] else "USB")

        self._running = True
        self._thread = threading.Thread(target=self._io, daemon=True)
        self._thread.start()

        if self._enable_startup_pulse:
            # Pulse confirms trigger writes are landing.
            pulse = (M_RIGID, 0, self._pulse_force)
            self.set(pulse, pulse); time.sleep(0.2)
            self.set(off(), off())

    def close(self):
        if not self.dev:
            return
        self.set(off(), off()); time.sleep(0.1)
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
        self.dev.close()
        self.dev = None

    def set(self, left, right):
        with self._lock:
            self._left, self._right, self._dirty = left, right, True

    def _io(self):
        # Non-blocking read keeps the BT input pipe drained without stalling
        # writes. We sleep tiny amounts when there's nothing to do.
        while self._running:
            try:
                try:
                    self.dev.read(self.lay["size"])  # returns immediately (nonblocking)
                except OSError:
                    pass  # BT read can fail randomly on Windows
                
                with self._lock:
                    if not self._dirty:
                        time.sleep(0.001)
                        continue
                    left, right, self._dirty = self._left, self._right, False
                
                self.dev.write(self._build(left, right))
            except Exception:
                log.exception("HID write failed; stopping trigger thread")
                self._running = False
                break

    def _build(self, left, right):
        L = self.lay
        buf = bytearray(L["size"])
        buf[0] = L["rid"]
        if L["bt"]:
            buf[1] = 0x02
        buf[L["flags"]] = TRIG_FLAGS
        for pos, (mode, p1, p2) in ((L["r"], right), (L["l"], left)):
            buf[pos]     = mode
            buf[pos + 1] = p1
            buf[pos + 2] = p2
        if L["bt"]:
            struct.pack_into("<I", buf, 74, zlib.crc32(b"\xA2" + bytes(buf[:74])))
        return bytes(buf)
