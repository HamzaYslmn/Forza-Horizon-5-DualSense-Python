"""FH5 DualSense building blocks — DualSense HID, UDP listener, settings."""
import logging
import os
import sys

from . import dualsense, udplistener, loop, exit_detection


def install_file_logging(path) -> None:
    """Add a FileHandler so crashes survive a closed terminal window.
    Truncates on each run so the file always reflects the current session."""
    fh = logging.FileHandler(path, mode="w", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    fh.setLevel(logging.DEBUG)
    root = logging.getLogger()
    root.addHandler(fh)
    if root.level > logging.DEBUG or root.level == 0:
        root.setLevel(logging.DEBUG)

def setup_logging(debug: bool = False) -> None:
    """Configures the root logger with a colorful formatter if supported."""
    if os.name == "nt":
        os.system("")  # Enable ANSI color in Windows CMD

    class ColorFormatter(logging.Formatter):
        COLORS = {
            logging.DEBUG: '\033[96m',    # Cyan
            logging.INFO: '\033[92m',     # Green
            logging.WARNING: '\033[93m',  # Yellow
            logging.ERROR: '\033[91m',    # Red
            logging.CRITICAL: '\033[91m', # Red
        }
        def format(self, record):
            s = super().format(record)
            c = self.COLORS.get(record.levelno)
            return f"{c}{s}\033[0m" if c else s

    has_colors = sys.stderr.isatty()
    
    if has_colors:
        formatter = ColorFormatter("%(asctime)s %(message)s")
    else:
        formatter = logging.Formatter("%(asctime)s %(message)s")

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        handlers=[handler],
        force=True,
    )
