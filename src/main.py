import argparse
import logging
import sys

from modules import dualsense, udplistener, setup_logging, loop
from modules import preferences
from modules.settings import Settings
from modules.update_check import log_latest_commit_age

log = logging.getLogger("fh5ds")


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

    if not use_tui:
        setup_logging(args.debug)
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
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
