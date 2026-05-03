import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from modules import dualsense, udplistener, setup_logging, install_file_logging, loop
from modules import preferences
from modules.settings import Settings
from modules.update_check import log_latest_commit_age

log = logging.getLogger("fh5ds")

LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_KEEP = 10  # number of past run logs to retain


def _prepare_log_file() -> Path:
    LOG_DIR.mkdir(exist_ok=True)
    # Prune older logs first so a crashing app can't fill the disk.
    for old in sorted(LOG_DIR.glob("fh5ds_*.log"), reverse=True)[LOG_KEEP - 1:]:
        try:
            old.unlink()
        except OSError:
            pass
    return LOG_DIR / f"fh5ds_{datetime.now():%Y%m%d_%H%M%S}.log"


def run(s: Settings) -> None:
    ds = dualsense.DualSense(
        startup_pulse_force=s.startup_pulse_force,
        enable_startup_pulse=s.enable_startup_pulse,
    )
    ds.open()
    try:
        with udplistener.UDPListener(s.udp_host, s.udp_port, s.udp_timeout) as listener:
            log.info("Listening on %s:%d | Ctrl+C to quit", s.udp_host, s.udp_port)
            log.info("  In FH5: HUD & Gameplay -> Data Out: ON, IP 127.0.0.1, Port %d", s.udp_port)
            loop.run(ds, listener, s)
    finally:
        ds.close()


def run_tui(s: Settings) -> None:
    from modules.tui import TriggerTUI
    TriggerTUI(s).run()


def _excepthook(exc_type, exc, tb):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc, tb)
        return
    logging.getLogger("fh5ds").critical("Unhandled exception", exc_info=(exc_type, exc, tb))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="FH5 DualSense adaptive triggers (Steam keeps rumble)")
    p.add_argument("--host", default="127.0.0.1", help="UDP bind address (overrides Settings)")
    p.add_argument("--port", type=int, default=None, help="UDP port (overrides Settings)")
    p.add_argument("--debug", action="store_true", help="Verbose per-packet logs")
    p.add_argument("--no-tui", action="store_true", help="Disable the textual UI and use console logs")
    args = p.parse_args()

    settings = Settings()
    preferences.load(settings)
    if args.host is not None: settings.udp_host = args.host
    if args.port is not None: settings.udp_port = args.port

    use_tui = not args.no_tui

    log_file = _prepare_log_file()
    if not use_tui:
        setup_logging(args.debug)
    install_file_logging(log_file)
    sys.excepthook = _excepthook
    log.info("Log file: %s", log_file)

    if not use_tui:
        log_latest_commit_age()
        log.debug("Debug logging enabled")

    try:
        if use_tui:
            run_tui(settings)
        else:
            run(settings)
    except KeyboardInterrupt:
        sys.exit(0)
    except RuntimeError as e:
        log.critical("RuntimeError: %s", e)
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
