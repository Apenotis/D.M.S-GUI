import configparser
import os
import sys

# ============================================================================
# Paths and constants
# ============================================================================
APP_VERSION = "3.2.4"


def _resolve_base_dir() -> str:
    """Resolve the working directory consistently for source and frozen builds."""
    if getattr(sys, "frozen", False):
        # For PyInstaller builds, point to the EXE directory, not _internal.
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _resolve_assets_dir() -> str:
    """Resolve the assets directory (bundled via --add-data into _MEIPASS)."""
    if getattr(sys, "frozen", False):
        # PyInstaller 6+: --add-data files land in sys._MEIPASS, not next to the EXE.
        return os.path.join(sys._MEIPASS, "assets")
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")


BASE_DIR = _resolve_base_dir()
ASSETS_DIR = _resolve_assets_dir()
CONFIG_FILE = os.path.join(BASE_DIR, "config.ini")
IWAD_DIR = os.path.join(BASE_DIR, "iwad")
PWAD_DIR = os.path.join(BASE_DIR, "pwad")
CSV_FILE = os.path.join(BASE_DIR, "maps.csv")
DB_FILE = os.path.join(BASE_DIR, "maps.db")
ENGINE_BASE_DIR = os.path.join(BASE_DIR, "Engines")

# ============================================================================
# Engine lists and repos
# ============================================================================
SUPPORTED_ENGINES = [
    "gzdoom", "uzdoom", "dsda-doom", "woof",
    "nugget-doom", "odamex", "zandronum", "lzdoom"
]

ENGINE_REPOS = {
    "gzdoom": "ZDoom/gzdoom",
    "uzdoom": "UZDoom/UZDoom",
    "dsda-doom": "kraflab/dsda-doom",
    "woof": "fabiangreffrath/woof",
    "nugget-doom": "MrAlaux/Nugget-Doom",
    "odamex": "odamex/odamex",
    "zandronum": "Zandronum/zandronum",
    "lzdoom": "ZDoom/lzdoom"
}

# Optional: map individual engines to direct ZIP URLs if the GitHub API is blocked.
DIRECT_DOWNLOADS = {}

# Fallback for launcher update checks. config.ini values take precedence.
UPDATE_URL = ""

# ============================================================================
# Initialization
# ============================================================================
config = configparser.ConfigParser()


def save_config():
    """Write the current config state safely using UTF-8-SIG."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8-sig") as f:
            config.write(f)
    except Exception as e:
        print(f"Error writing config.ini: {e}")


def load_config():
    """Reload configuration from disk."""
    if os.path.exists(CONFIG_FILE):
        config.read(CONFIG_FILE, encoding="utf-8-sig")

    for sec in ["SETTINGS", "STATS", "UPDATE"]:
        if sec not in config:
            config.add_section(sec)

    global CURRENT_ENGINE
    CURRENT_ENGINE = config.get("SETTINGS", "current_engine", fallback="gzdoom")


def get_current_engine():
    """Return the name of the currently selected engine."""
    config.read(CONFIG_FILE, encoding="utf-8-sig")
    return config.get("SETTINGS", "current_engine", fallback="gzdoom")


def get_engine_path():
    """Build the full path to the current engine executable."""
    name = get_current_engine()
    return os.path.join(ENGINE_BASE_DIR, name, f"{name}.exe")


def update_config_value(section, key, value):
    """Update a config value and save it immediately."""
    section = section.upper()
    if not config.has_section(section):
        config.add_section(section)
    config.set(section, key, str(value))
    save_config()
    load_config()


def set_stat(key, value):
    """Convenience helper for statistics values such as playtime."""
    if "STATS" not in config:
        config.add_section("STATS")
    config.set("STATS", key, str(value))
    save_config()


def get_launcher_update_url() -> str:
    """Resolve the launcher update source from config.ini."""
    direct_url = config.get("UPDATE", "launcher_update_url", fallback="").strip()
    if direct_url:
        return direct_url

    repo = config.get("UPDATE", "launcher_repo", fallback="").strip()
    branch = config.get("UPDATE", "launcher_branch", fallback="main").strip() or "main"
    file_path = config.get("UPDATE", "launcher_file", fallback="Gui.py").strip() or "Gui.py"
    if repo:
        normalized = file_path.replace("\\", "/")
        return f"https://raw.githubusercontent.com/{repo}/{branch}/{normalized}"

    return UPDATE_URL


def get_launcher_version_url() -> str:
    """Resolve the version source used for launcher update checks."""
    direct_url = config.get("UPDATE", "launcher_update_url", fallback="").strip()
    if direct_url:
        return direct_url

    repo = config.get("UPDATE", "launcher_repo", fallback="").strip()
    branch = config.get("UPDATE", "launcher_branch", fallback="main").strip() or "main"
    version_file = config.get("UPDATE", "launcher_version_file", fallback="dms_core/config.py").strip() or "dms_core/config.py"
    if repo:
        normalized = version_file.replace("\\", "/")
        return f"https://raw.githubusercontent.com/{repo}/{branch}/{normalized}"

    return UPDATE_URL


load_config()
