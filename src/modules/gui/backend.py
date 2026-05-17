"""Backend lifecycle owner: DualSense + UDP listener + per-frame loop thread.

Pulled out of `TriggerGUI` so the GUI orchestrator stays focused on widgets
and so the same controller can be reused by an alternative frontend (e.g. a
headless wrapper or a future Qt port) without dragging Tk-specific code with
it.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from modules import dualsense, loop, udplistener
from modules.dualsense.triggers import off, vibration
from modules.settings import Settings

log = logging.getLogger("fhds")

HAPTIC_FREQ_HZ = 40
HAPTIC_AMP_ON = 200
HAPTIC_AMP_OFF = 120
HAPTIC_DURATION_S = 0.10


class BackendController:
    """Owns the DualSense, UDP listener and per-frame loop thread.

    Lifecycle:
        ctrl = BackendController(settings)
        ctrl.on_loop_exit = lambda: ...   # called from worker thread
        if ctrl.start():
            ...                            # backend running on a daemon thread
            ctrl.stop()                    # idempotent; safe to call from teardown

    The instance is single-use — call `start()` at most once. The shutdown
    order matters: clearing `stop_event` releases the loop, joining the thread
    ensures it sees the release before we close the HID device underneath it.
    """

    JOIN_TIMEOUT_S = 2.0

    def __init__(self, settings: Settings):
        self.settings = settings
        self.on_loop_exit: Callable[[], None] | None = None

        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._ds: dualsense.DualSense | None = None
        self._listener_cm: udplistener.UDPListener | None = None
        self._listener = None
        self._stopped = False
        self._startup_error: BaseException | None = None

    # MARK: Public state
    @property
    def is_connected(self) -> bool:
        return bool(self._ds and self._ds.connected)

    @property
    def startup_error(self) -> BaseException | None:
        return self._startup_error

    # MARK: Lifecycle
    def start(self) -> bool:
        """Open hardware and start the per-frame loop on a daemon thread.

        Returns True on success. On failure logs the exception, stores it on
        `startup_error`, and returns False without partial state — any objects
        opened before the failure are torn down before returning.
        """
        s = self.settings
        try:
            self._ds = dualsense.DualSense(
                startup_pulse_force=s.startup_pulse_force,
                enable_startup_pulse=s.enable_startup_pulse,
                reconnect_interval_s=s.reconnect_interval_s,
            )
            self._ds.open()
            self._listener_cm = udplistener.UDPListener(s.udp_host, s.udp_port, s.udp_timeout)
            self._listener = self._listener_cm.__enter__()
        except Exception as exc:
            log.exception("Backend startup failed")
            self._startup_error = exc
            self._close_resources()
            return False

        log.info("Listening on %s:%d", s.udp_host, s.udp_port)
        log.info("In game: HUD & Gameplay -> Data Out: ON, IP %s, Port %d",
                 s.udp_host, s.udp_port)
        self._thread = threading.Thread(target=self._run_loop, daemon=True,
                                        name="fhds-loop")
        self._thread.start()
        return True

    def stop(self) -> None:
        """Stop the loop, join the thread, close the listener and HID device.

        Idempotent — safe to call multiple times (e.g. from both the window
        close handler and a `finally` in the entry point).
        """
        if self._stopped:
            return
        self._stopped = True
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=self.JOIN_TIMEOUT_S)
        self._close_resources()

    # MARK: Switch-toggle haptic confirm
    def confirm_toggle(self, on: bool) -> None:
        """Pulse the trigger to confirm a switch was flipped.

        Fire-and-forget — runs on a one-shot daemon thread so a slow HID write
        can never block the UI event loop.
        """
        if not self.is_connected:
            return
        threading.Thread(target=self._do_haptic, args=(on,), daemon=True,
                         name="fhds-confirm").start()

    # MARK: Internals
    def _run_loop(self) -> None:
        try:
            loop.run(self._ds, self._listener, self.settings, stop_event=self._stop)
        finally:
            # Notify the orchestrator IFF the loop returned on its own (game
            # closed, telemetry-lost). On a user-requested stop the orchestrator
            # is already in the middle of teardown and a callback would race.
            if not self._stop.is_set() and self.on_loop_exit is not None:
                try:
                    self.on_loop_exit()
                except Exception:
                    log.exception("on_loop_exit callback raised")

    def _do_haptic(self, on: bool) -> None:
        ds = self._ds
        if ds is None:
            return
        amp = HAPTIC_AMP_ON if on else HAPTIC_AMP_OFF
        v = vibration(HAPTIC_FREQ_HZ, amp)
        try:
            ds.set(v, v)
            time.sleep(HAPTIC_DURATION_S)
            ds.set(off(), off())
        except Exception:
            # The controller can disappear between the connected-check and the
            # HID write; treat haptic confirm as best-effort and stay silent.
            pass

    def _close_resources(self) -> None:
        if self._listener_cm is not None:
            try:
                self._listener_cm.__exit__(None, None, None)
            except Exception:
                log.debug("UDP listener close failed", exc_info=True)
            self._listener_cm = None
            self._listener = None
        if self._ds is not None:
            try:
                self._ds.close()
            except Exception:
                log.debug("DualSense close failed", exc_info=True)
            self._ds = None
