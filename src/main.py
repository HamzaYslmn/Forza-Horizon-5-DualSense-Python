import argparse
import logging
import sys
import traceback
from datetime import datetime
from pathlib import Path

from modules import dualsense, udplistener, setup_logging, loop
from modules import preferences
from modules.settings import Settings
from modules.update_check import log_latest_commit_age

log = logging.getLogger("fhds")

# MARK: Crash log — only written on unhandled exceptions
CRASH_LOG = Path(__file__).resolve().parent / "crash.log"


def _excepthook(exc_type, exc, tb):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc, tb)
        return
    try:
        with open(CRASH_LOG, "w", encoding="utf-8") as f:
            f.write(f"Crash at {datetime.now():%Y-%m-%d %H:%M:%S}\n\n")
            traceback.print_exception(exc_type, exc, tb, file=f)
    except OSError:
        pass
    log.critical("Unhandled exception", exc_info=(exc_type, exc, tb))


def run(s: Settings) -> None:
    ds = dualsense.DualSense(
        startup_pulse_force=s.startup_pulse_force,
        enable_startup_pulse=s.enable_startup_pulse,
        reconnect_interval_s=s.reconnect_interval_s,
    )
    ds.open()
    try:
        with udplistener.UDPListener(s.udp_host, s.udp_port, s.udp_timeout) as listener:
            log.info("Listening on %s:%d | Ctrl+C to quit", s.udp_host, s.udp_port)
            log.info("  In game: HUD & Gameplay -> Data Out: ON, IP 127.0.0.1, Port %d", s.udp_port)
            loop.run(ds, listener, s)
    finally:
        ds.close()


def run_tui(s: Settings) -> None:
    from modules.tui import TriggerTUI
    TriggerTUI(s).run()


# MARK: Entry point
if __name__ == "__main__":
    p = argparse.ArgumentParser(description="FH DualSense adaptive triggers (Steam keeps rumble)")
    p.add_argument("--host", default="127.0.0.1", help="UDP bind address")
    p.add_argument("--port", type=int, default=None, help="UDP port")
    p.add_argument("--debug", action="store_true", help="Verbose per-packet logs")
    p.add_argument("--headless", action="store_true", help="Disable TUI, use console logs")
    args = p.parse_args()

    settings = Settings()
    preferences.load(settings)
    if args.host is not None: settings.udp_host = args.host
    if args.port is not None: settings.udp_port = args.port

    sys.excepthook = _excepthook

    if args.headless:
        setup_logging(args.debug)
        log_latest_commit_age()
        run(settings)
    else:
        run_tui(settings)
