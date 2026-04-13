import glob
import json
import os
import re
import shutil
import sys
import time
import urllib.request

import dms_core.config as cfg

# ============================================================================
# LAUNCHER & ENGINE UPDATES
# ============================================================================

def check_uzdoom_update() -> tuple[bool, str]:
    """
    Prüft über die GitHub API, ob eine neuere Version der UZDoom Engine verfügbar ist.
    Gibt ein Tuple zurück: (Ist_Neuer_als_4.14.3, Neueste_Version_String).
    """
    try:
        req = urllib.request.Request("https://api.github.com/repos/UZDoom/UZDoom/releases/latest")
        req.add_header("User-Agent", "Python-Launcher")
        with urllib.request.urlopen(req, timeout=2) as response:
            data = json.loads(response.read().decode())
            latest = data.get("tag_name", "")
            return latest != "4.14.3", latest
    except Exception as e:
        print(f"[UPDATER] Fehler beim Prüfen auf UZDoom Update: {e}")
        return False, "4.14.3"

def is_newer(remote: str, local: str) -> bool:
    """Vergleicht Versions-Strings wie '3.1' oder '3.0.5' mathematisch."""
    try:
        # Zerlegt '3.1.0' in [3, 1, 0] für den korrekten Listen-Vergleich
        remote_parts = [int(x) for x in str(remote).split(".")]
        local_parts = [int(x) for x in str(local).split(".")]
        return remote_parts > local_parts
    except Exception:
        return False


def _fetch_text(url: str, timeout: int = 5) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8-sig")


def _get_launcher_target_path() -> str:
    target_rel = cfg.config.get("UPDATE", "launcher_file", fallback="Gui.py").strip() or "Gui.py"
    target_path = os.path.abspath(os.path.join(cfg.BASE_DIR, target_rel))
    base_dir = os.path.abspath(cfg.BASE_DIR)

    # Security guard: updates may only write python files inside BASE_DIR.
    if not target_path.startswith(base_dir + os.sep):
        raise ValueError(f"Unsicherer Update-Pfad ausserhalb BASE_DIR: {target_path}")
    if not target_path.lower().endswith(".py"):
        raise ValueError(f"Update-Zieldatei ist keine Python-Datei: {target_path}")

    return target_path

def check_launcher_update() -> dict:
    """
    Prüft auf der angegebenen UPDATE_URL, ob eine neuere Version des Launchers vorliegt.
    Gibt ein Dictionary zurück, das von der GUI verarbeitet werden kann.
    """
    result = {"update_available": False, "remote_version": "", "remote_code": "", "error": None}
    
    try:
        update_url = cfg.get_launcher_update_url()
        version_url = cfg.get_launcher_version_url()
        if not update_url:
            result["error"] = "Launcher-Updatequelle nicht konfiguriert (UPDATE.launcher_update_url oder launcher_repo)."
            return result
        if not version_url:
            result["error"] = "Launcher-Versionsquelle nicht konfiguriert."
            return result

        version_code = _fetch_text(version_url, timeout=5)
        remote_code = _fetch_text(update_url, timeout=5)

        match = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', version_code)
        if match:
            remote_version = match.group(1)
            result["remote_version"] = remote_version
            result["remote_code"] = remote_code

            if is_newer(remote_version, cfg.APP_VERSION):
                result["update_available"] = True
                
    except Exception as e:
        result["error"] = str(e)
        print(f"[UPDATER] Fehler beim Update-Check: {e}")

    return result

def apply_launcher_update(remote_version: str, remote_code: str) -> bool:
    """
    Führt das Auto-Update durch, erstellt Backups (Script & CSV) und
    schreibt den neuen Code. Muss von der Hauptdatei oder GUI gerufen werden, 
    die danach einen Neustart initiiert.
    """
    try:
        target_path = _get_launcher_target_path()

        # Plausibility check for GUI updates: prevent writing unrelated files into Gui.py.
        if os.path.basename(target_path).lower() == "gui.py":
            if "class DoomManagerGUI" not in remote_code:
                raise ValueError("Remote-Code sieht nicht wie Gui.py aus (DoomManagerGUI fehlt).")

        # 1. Script Backup
        backup_path = f"{target_path}.bak_v{cfg.APP_VERSION}"
        shutil.copy2(target_path, backup_path)

        # 2. Datenbank Backup
        if os.path.exists(cfg.DB_FILE):
            db_backup_path = f"{cfg.DB_FILE}.bak_v{cfg.APP_VERSION}"
            shutil.copy2(cfg.DB_FILE, db_backup_path)

        # Update schreiben
        remote_code_fixed = remote_code.replace("\r\n", "\n")
        with open(target_path, "w", encoding="utf-8-sig") as f:
            f.write(remote_code_fixed)

        return True
    except Exception as e:
        print(f"[UPDATER] Fehler beim Anwenden des Updates: {e}")
        return False

def get_available_backups() -> list:
    """
    Sucht nach vorhandenen Backups (.bak_v*) und gibt eine Liste zurück.
    """
    target_path = _get_launcher_target_path()
    backup_files = sorted(glob.glob(f"{target_path}.bak_v*"), reverse=True)
    return backup_files

def apply_rollback(backup_file_path: str) -> bool:
    """
    Stellt eine ältere Version des Scripts sowie der dazugehörigen Datenbank wieder her.
    """
    try:
        target_path = _get_launcher_target_path()
        version_suffix = backup_file_path.split(".bak_")[-1]
        selected_db_bak = f"{cfg.DB_FILE}.bak_{version_suffix}"

        # Aktuellen Zustand als "Broken" sichern
        shutil.copy2(target_path, f"{target_path}.broken")
        if os.path.exists(cfg.DB_FILE):
            shutil.copy2(cfg.DB_FILE, f"{cfg.DB_FILE}.broken")

        # Wiederherstellung Script
        shutil.copy2(backup_file_path, target_path)

        # Wiederherstellung Datenbank (falls Backup existiert)
        if os.path.exists(selected_db_bak):
            shutil.copy2(selected_db_bak, cfg.DB_FILE)

        return True
    except Exception as e:
        print(f"[UPDATER] Fehler beim Rollback: {e}")
        return False