import argparse
import logging
import sys
import traceback
from datetime import datetime
from pathlib import Path

from modules import dualsense, udplistener, setup_logging, loop, profiles
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


def run_gui(s: Settings, debug: bool) -> bool:
    """Launch the CustomTkinter GUI. Returns False if the GUI stack can't be
    loaded (e.g. `tkinter` missing on a minimal Linux install) so the caller
    can fall back to headless mode."""
    try:
        from modules.gui import TriggerGUI  # noqa: PLC0415 — import after Tk check
    except ImportError as exc:
        # Most common cause on Linux: python3-tk not installed. Print a clear
        # install hint to stderr before falling through.
        sys.stderr.write(
            "\n[fhds] GUI dependencies are missing: "
            f"{exc.name or exc}.\n"
            "[fhds] On Debian/Ubuntu:  sudo apt install python3-tk\n"
            "[fhds] On Fedora:         sudo dnf install python3-tkinter\n"
            "[fhds] On Arch:           sudo pacman -S tk\n"
            "[fhds] Falling back to headless mode.\n\n"
        )
        return False
    TriggerGUI(s).run()
    return True


# MARK: Entry point
if __name__ == "__main__":
    p = argparse.ArgumentParser(description="FH DualSense adaptive triggers (Steam keeps rumble)")
    p.add_argument("--host", default="127.0.0.1", help="UDP bind address")
    p.add_argument("--port", type=int, default=None, help="UDP port")
    p.add_argument("--debug", action="store_true", help="Verbose per-packet logs")
    p.add_argument("--gui", action="store_true",
                   help="Opt in to the experimental CustomTkinter desktop GUI. "
                        "Default is headless (console logs) — the GUI is still "
                        "rough around window-resize performance.")
    p.add_argument("--headless", action="store_true",
                   help="Explicitly request headless mode (this is the default).")
    p.add_argument("--profile", default=None,
                   help="Load this named tuning profile at startup (created if missing)")
    # --no-tui kept as a hidden alias so existing Steam Launch Options keep working.
    # Since headless is now the default, --no-tui is effectively a no-op but
    # logs a one-line deprecation hint.
    p.add_argument("--no-tui", dest="no_tui", action="store_true", help=argparse.SUPPRESS)
    args = p.parse_args()

    settings = Settings()
    try:
        profiles.load_or_migrate(settings, requested=args.profile)
    except profiles.InvalidProfileName as e:
        sys.stderr.write(f"[fhds] Invalid --profile value: {e}\n")
        sys.exit(2)
    if args.host is not None: settings.udp_host = args.host
    if args.port is not None: settings.udp_port = args.port

    sys.excepthook = _excepthook

    if args.no_tui:
        sys.stderr.write("[fhds] --no-tui is a no-op (headless is the default). "
                         "Pass --gui to launch the experimental window.\n")

    if args.gui:
        if run_gui(settings, args.debug):
            sys.exit(0)
        # GUI couldn't load — fall through to headless so the user still
        # gets working triggers. `run_gui` already printed the install hint.
    setup_logging(args.debug)
    log_latest_commit_age()
    run(settings)
