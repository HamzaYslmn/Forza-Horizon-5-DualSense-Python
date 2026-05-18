import logging
import struct
import sys
import threading
import time
import zlib

# PyPI's hidapi Linux wheel uses libusb, which can't claim the gamepad interface
# (hid-playstation kernel driver owns it). Use a direct /dev/hidraw shim instead.
if sys.platform.startswith("linux"):
    from . import _hidraw as hid
else:
    import hid

from .triggers import M_RIGID, off

log = logging.getLogger("fhds.dualsense")

VENDOR_ID = 0x054C
PRODUCT_IDS = (0x0CE6, 0x0DF2)  # DualSense, DualSense Edge

# valid_flag0: 0x01 (R motor), 0x02 (L motor), 0x04 (R trigger), 0x08 (L trigger).
# Some firmware needs motor bits set for trigger bits to be processed.
TRIG_FLAGS = 0x01 | 0x02 | 0x04 | 0x08

# MARK: Layout maps — byte offsets per transport
# vf1 = valid_flag1, psav = power_save_control
USB = {"rid": 0x02, "flags": 1, "vf1": 2, "psav": 10, "r": 11, "l": 22, "size": 64, "bt": False}
BT  = {"rid": 0x31, "flags": 2, "vf1": 3, "psav": 11, "r": 12, "l": 23, "size": 78, "bt": True}


def _enumerate_dualsenses():
    return [d for d in hid.enumerate(VENDOR_ID, 0)
            if d.get("product_id") in PRODUCT_IDS]


def _find_gamepad():
    """Pick the Game Pad HID interface (usage_page=1, usage=5) or None.
    Audio/sensor interfaces share VID/PID and silently drop trigger writes."""
    devices = _enumerate_dualsenses()
    for d in devices:
        if d.get("usage_page", 1) == 1 and d.get("usage", 5) == 5:
            return d
    return devices[0] if devices else None


def _is_bluetooth(info):
    """Detect BT across hidapi backends.

    bus_type values seen in the wild:
      - hidapi-windows:   USB=1, Bluetooth=2
      - hidapi-libusb:    follows libusb (USB always)
      - hidapi-hidraw (Linux): BUS_USB=3, BUS_BLUETOOTH=5
    """
    bus_type = info.get("bus_type")
    if bus_type is not None:
        if bus_type in (2, 5):
            return True
        if bus_type in (1, 3):
            return False
    path = info.get("path", b"")
    if isinstance(path, str):
        path = path.encode()
    path_upper = path.upper()
    if b"BTHENUM" in path_upper or b"BLUETOOTH" in path_upper:
        return True
    # Linux hidraw nodes don't carry bus info in the path; fall back to USB.
    return False


def _log_open_failure(err) -> None:
    # hidapi's "open failed" is opaque; on Linux it almost always means the
    # hidraw node is root-only because the udev rule isn't installed.
    if sys.platform.startswith("linux"):
        log.error(
            "DualSense open failed (%s). Install the udev rule:\n"
            "  sudo cp packaging/linux/70-dualsense.rules /etc/udev/rules.d/\n"
            "  sudo udevadm control --reload-rules && sudo udevadm trigger\n"
            "Then unplug/replug (USB) or re-pair (Bluetooth).", err,
        )
    else:
        log.warning("DualSense open failed (%s) — another app may be holding it open.", err)


class DualSense:
    """Triggers-only DualSense writer. Steam keeps rumble bits untouched.

    Resilient: starts without a controller and retries every
    ``reconnect_interval_s`` seconds. Drops writes silently while disconnected.
    """

    def __init__(
        self,
        startup_pulse_force: int = 180,
        enable_startup_pulse: bool = True,
        reconnect_interval_s: float = 5.0,
    ):
        self.dev = None
        self.dev_path = None
        self.lay = USB
        self._lock = threading.Lock()
        self._left = self._right = off()
        self._dirty = False
        self._running = False
        self._thread = None
        self._pulse_force = startup_pulse_force
        self._enable_startup_pulse = enable_startup_pulse
        self._reconnect_interval = reconnect_interval_s
        self._open_hinted = False
        # Re-enumerate HID while connected to detect silent unplugs — Windows
        # hidapi's write() can return -1 on a stale handle without raising.
        self._presence_check_interval = 5.0
        self._last_presence_check = 0.0
        # Idle-input watchdog — DualSense streams input reports continuously
        # (hundreds of Hz). On a Bluetooth drop, Windows keeps the HID node
        # alive and writes get buffered, but the input stream stops cold.
        self._input_idle_timeout = 3.0
        self._last_input_at = 0.0

    @property
    def connected(self) -> bool:
        return self.dev is not None

    def open(self):
        """Start the I/O thread. Never raises if the controller is absent."""
        self._running = True
        self._thread = threading.Thread(target=self._io, daemon=True)
        self._thread.start()

    def close(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        self._disconnect()

    def set(self, left, right):
        with self._lock:
            self._left, self._right, self._dirty = left, right, True

    # MARK: connect / disconnect helpers
    def _try_connect(self) -> bool:
        info = _find_gamepad()
        if not info:
            return False
        try:
            dev = hid.device()
            dev.open_path(info["path"])
            dev.set_nonblocking(True)
        except (OSError, IOError) as e:
            if not self._open_hinted:
                _log_open_failure(e)
                self._open_hinted = True
            return False
        self.dev = dev
        self.dev_path = info.get("path")
        self.lay = BT if _is_bluetooth(info) else USB
        self._open_hinted = False
        now = time.monotonic()
        self._last_presence_check = now
        self._last_input_at = now
        log.info("DualSense connected (%s)", "BT" if self.lay["bt"] else "USB")

        if self._enable_startup_pulse:
            try:
                pulse = (M_RIGID, (0, self._pulse_force))
                self.dev.write(self._build(pulse, pulse)); time.sleep(0.2)
                self.dev.write(self._build(off(), off()))
            except Exception:
                pass
        # MARK: Power saver — one-shot at connect
        try:
            self.dev.write(self._build_power_saver())
        except Exception:
            pass
        return True

    def _disconnect(self, reason: str = ""):
        was_connected = self.dev is not None
        if self.dev is not None:
            try:
                self.dev.write(self._build(off(), off()))
            except Exception:
                pass
            try:
                self.dev.close()
            except Exception:
                pass
        self.dev = None
        self.dev_path = None
        if was_connected:
            suffix = f" ({reason})" if reason else ""
            log.warning("DualSense disconnected%s — retrying every %.0fs",
                        suffix, self._reconnect_interval)

    def _device_still_present(self) -> bool:
        """Return True if our currently-open HID path still appears in enumeration."""
        if self.dev_path is None:
            return False
        try:
            devices = _enumerate_dualsenses()
        except Exception:
            # Enumeration error shouldn't itself force a disconnect.
            return True
        return any(d.get("path") == self.dev_path for d in devices)

    # MARK: I/O thread — connect, write while connected, reconnect on error
    def _io(self):
        last_attempt = -1e9
        announced_waiting = False
        while self._running:
            now = time.monotonic()
            if not self.connected:
                if now - last_attempt < self._reconnect_interval:
                    time.sleep(0.1)
                    continue
                last_attempt = now
                if self._try_connect():
                    announced_waiting = False
                    continue
                if not announced_waiting:
                    log.info("Waiting for DualSense — retrying every %.0fs", self._reconnect_interval)
                    announced_waiting = True
                continue

            try:
                try:
                    data = self.dev.read(self.lay["size"])  # nonblocking drain
                except OSError:
                    self._disconnect("read failed")
                    continue
                if data:
                    self._last_input_at = now
                elif now - self._last_input_at >= self._input_idle_timeout:
                    self._disconnect(f"no input for {self._input_idle_timeout:.0f}s")
                    continue

                if now - self._last_presence_check >= self._presence_check_interval:
                    self._last_presence_check = now
                    if not self._device_still_present():
                        self._disconnect("no longer enumerated")
                        continue

                with self._lock:
                    if not self._dirty:
                        time.sleep(0.001)
                        continue
                    left, right, self._dirty = self._left, self._right, False

                n = self.dev.write(self._build(left, right))
                if n is not None and n <= 0:
                    self._disconnect(f"write returned {n}")
            except Exception as e:
                self._disconnect(f"write failed: {e}")

    def _new_report(self):
        L = self.lay
        buf = bytearray(L["size"])
        buf[0] = L["rid"]
        if L["bt"]:
            buf[1] = 0x02
        return buf

    def _finalize_bt_crc(self, buf):
        if self.lay["bt"]:
            struct.pack_into("<I", buf, 74, zlib.crc32(b"\xA2" + bytes(buf[:74])))

    def _build(self, left, right):
        L = self.lay
        buf = self._new_report()
        buf[L["flags"]] = TRIG_FLAGS
        for pos, (mode, params) in ((L["r"], right), (L["l"], left)):
            buf[pos] = mode
            for i, b in enumerate(params[:10]):
                buf[pos + 1 + i] = b & 0xFF
        self._finalize_bt_crc(buf)
        return bytes(buf)

    def _build_power_saver(self):
        """Build a minimal HID report that enables the power-save flag only."""
        L = self.lay
        buf = self._new_report()
        buf[L["vf1"]] |= 0x02          # bit 1 = POWER_SAVE_CONTROL enable
        buf[L["psav"]] |= 0x10         # bit 4 = hardware power save
        self._finalize_bt_crc(buf)
        return bytes(buf)
