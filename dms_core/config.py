import configparser
import os

# ============================================================================
# PFADE & KONSTANTEN
# ============================================================================
APP_VERSION = "3.1"
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(BASE_DIR, "config.ini")
IWAD_DIR = os.path.join(BASE_DIR, "iwad")
PWAD_DIR = os.path.join(BASE_DIR, "pwad")
CSV_FILE = os.path.join(BASE_DIR, "maps.csv")
DB_FILE = os.path.join(BASE_DIR, "maps.db")
ENGINE_BASE_DIR = os.path.join(BASE_DIR, "Engines")

# ============================================================================
# ENGINE LISTEN & REPOS
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

# Optional: einzelne Engines auf direkte ZIP-URL mappen (z.B. falls GitHub API blockiert ist).
DIRECT_DOWNLOADS = {}

# Fallback fuer den Launcher-Updatecheck (wird bevorzugt aus config.ini gelesen).
UPDATE_URL = ""

# ============================================================================
# INITIALISIERUNG
# ============================================================================
config = configparser.ConfigParser()

def save_config():
    """Schreibt den aktuellen Zustand sicher in die Datei (UTF-8-SIG gegen Bug)."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8-sig") as f:
            config.write(f)
    except Exception as e:
        print(f"❌ Fehler beim Schreiben der config.ini: {e}")

def load_config():
    """Lädt die Konfiguration frisch von der Festplatte."""
    if os.path.exists(CONFIG_FILE):
        config.read(CONFIG_FILE, encoding="utf-8-sig")
    
    # Sicherstellen, dass Sektionen existieren
    for sec in ["SETTINGS", "STATS", "UPDATE"]:
        if sec not in config:
            config.add_section(sec)
    
    # Globale Variablen synchronisieren
    global CURRENT_ENGINE, USE_MODS
    CURRENT_ENGINE = config.get("SETTINGS", "current_engine", fallback="gzdoom")
    USE_MODS = config.getboolean("SETTINGS", "use_mods", fallback=True)

# ============================================================================
# FUNKTIONEN FÜR DIE GUI & STATISTIKEN
# ============================================================================

def get_current_engine():
    """Gibt den Namen der aktuell gewählten Engine zurück."""
    config.read(CONFIG_FILE, encoding="utf-8-sig")
    return config.get("SETTINGS", "current_engine", fallback="gzdoom")

def get_engine_path():
    """Baut den kompletten Pfad zur EXE der aktuellen Engine."""
    name = get_current_engine()
    return os.path.join(ENGINE_BASE_DIR, name, f"{name}.exe")

def update_config_value(section, key, value):
    """Aktualisiert einen Wert und speichert sofort."""
    section = section.upper()
    if not config.has_section(section):
        config.add_section(section)
    config.set(section, key, str(value))
    save_config()
    load_config()

def set_stat(key, value):
    """Spezialfunktion für Statistik-Werte (Spielzeit etc.)."""
    if "STATS" not in config:
        config.add_section("STATS")
    config.set("STATS", key, str(value))
    save_config()


def get_launcher_update_url() -> str:
    """Ermittelt die Update-Quelle fuer den Launcher aus der config.ini."""
    # 1) Direkte URL hat Vorrang
    direct_url = config.get("UPDATE", "launcher_update_url", fallback="").strip()
    if direct_url:
        return direct_url

    # 2) Optional aus Repo/Branch/Datei zusammensetzen
    repo = config.get("UPDATE", "launcher_repo", fallback="").strip()
    branch = config.get("UPDATE", "launcher_branch", fallback="main").strip() or "main"
    file_path = config.get("UPDATE", "launcher_file", fallback="Gui.py").strip() or "Gui.py"
    if repo:
        normalized = file_path.replace("\\", "/")
        return f"https://raw.githubusercontent.com/{repo}/{branch}/{normalized}"

    # 3) Fallback-Konstante
    return UPDATE_URL

# Initiales Laden beim Start
load_config()