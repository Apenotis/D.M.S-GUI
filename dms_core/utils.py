import functools
import logging
import math
import os
import re
import sys
import traceback

import dms_core.config as cfg

# ============================================================================
# TRACKER SETUP
# ============================================================================

tracker_log = logging.getLogger("DMS_Tracker")
tracker_log.setLevel(logging.DEBUG)
tracker_log.propagate = False
legacy_tracker_log = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dms_tracker.log")

def _ensure_tracker_handlers():
    """Initialize tracker handlers only once using console output only."""
    if tracker_log.handlers:
        return

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(logging.Formatter("[TRACKER] %(message)s"))
    tracker_log.addHandler(ch)


def is_tracker_enabled() -> bool:
    """Read the tracker switch from config.ini."""
    try:
        cfg.load_config()
        enabled = cfg.config.getboolean("SETTINGS", "tracker_enabled", fallback=False)
        if not enabled and os.path.exists(legacy_tracker_log):
            try:
                os.remove(legacy_tracker_log)
            except Exception:
                pass
        return enabled
    except Exception:
        return False

def tracker(func):
    """
    Decorator that logs the start, end, and crash of a function.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if not is_tracker_enabled():
            return func(*args, **kwargs)

        _ensure_tracker_handlers()

        tracker_log.debug(f"▶ START: {func.__name__}")
        try:
            result = func(*args, **kwargs)
            tracker_log.debug(f"✅ END:  {func.__name__} completed successfully.")
            return result
        except Exception as e:
            error_msg = f"❌ CRASH in {func.__name__}: {str(e)}\n{traceback.format_exc()}"
            tracker_log.error(error_msg)
            print(error_msg)  # Fallback in case the logger itself fails.
            raise 
    return wrapper

# ============================================================================
# Helper functions
# ============================================================================

def clear_screen():
    """Clear the console screen."""
    os.system("cls" if os.name == "nt" else "clear")

def resize_terminal(cols, lines):
    """Resize the terminal window when supported."""
    try:
        if os.name == "nt":
            # For the classic Windows cmd.exe
            os.system(f"mode con: cols={cols} lines={lines}")

        # ANSI escape sequence for Linux/macOS and compatible terminals
        sys.stdout.write(f"\x1b[8;{lines};{cols}t")
        sys.stdout.flush()
    except Exception:
        # Ignore terminals that do not support resizing, such as embedded GUI consoles.
        pass

def real_len(text):
    """Return the visible length of a string without ANSI color codes."""
    if not text:
        return 0
    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    return len(ansi_escape.sub("", str(text)))

def format_time(total_seconds):
    """Format seconds as a readable HH:MM:SS string."""
    try:
        total_seconds = int(total_seconds)
    except (ValueError, TypeError):
        total_seconds = 0
        
    h = math.floor(total_seconds / 3600)
    m = math.floor((total_seconds % 3600) / 60)
    s = total_seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"