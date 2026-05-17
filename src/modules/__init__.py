"""FH DualSense building blocks — DualSense HID, UDP listener, settings."""
import logging
import os

from . import dualsense, udplistener, loop, exit_detection

# MARK: Console logging setup (--headless mode only, TUI wires its own handler)
def setup_logging(debug: bool = False) -> None:
    if os.name == "nt":
        os.system("")  # enable ANSI escapes on Windows CMD

    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="\033[92m%(asctime)s %(message)s\033[0m",
        force=True,
    )
