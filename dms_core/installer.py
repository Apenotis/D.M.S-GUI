import csv
import os
import shutil
import zipfile

import dms_core.config as cfg
import dms_core.database as db
from dms_core.utils import tracker

# ============================================================================
# DEINE ERKENNUNGS-MATRIX FÜR OFFIZIELLE DATEIEN (IWAD ORDNER)
# ============================================================================
OFFICIAL_MAPPING = {
    "doom.wad":         {"Name": "Ultimate Doom", "IWAD": "doom.wad", "Kat": "IWAD", "Type": "DOOM"},
    "doom2.wad":        {"Name": "Doom II: Hell on Earth", "IWAD": "doom2.wad", "Kat": "IWAD", "Type": "DOOM"},
    "tnt.wad":          {"Name": "Final Doom: TNT:Evilution", "IWAD": "tnt.wad", "Kat": "IWAD", "Type": "DOOM"},
    "plutonia.wad":     {"Name": "Final Doom: The Plutonia Experiment", "IWAD": "plutonia.wad", "Kat": "IWAD", "Type": "DOOM"},
    "heretic.wad":      {"Name": "Heretic: Shadow of the Serpent Riders", "IWAD": "heretic.wad", "Kat": "EXTRA", "Type": "HERETIC"},
    "hexen.wad":        {"Name": "Hexen: Beyond Heretic", "IWAD": "hexen.wad", "Kat": "EXTRA", "Type": "HEXEN"},
    "hexdd.wad":        {"Name": "Hexen: Deathkings of the Dark Citadel", "IWAD": "hexen.wad", "Kat": "EXTRA", "Type": "HEXEN"},
    "sigil.wad":        {"Name": "Sigil", "IWAD": "doom.wad", "Kat": "IWAD", "Type": "DOOM"},
    "sigil2.wad":       {"Name": "Sigil 2", "IWAD": "doom.wad", "Kat": "IWAD", "Type": "DOOM"},
    "masterlevels.wad": {"Name": "Doom II: Masterlevels", "IWAD": "doom2.wad", "Kat": "IWAD", "Type": "DOOM"},
    "nerve.wad":        {"Name": "Doom II: No Rest for the Living", "IWAD": "doom2.wad", "Kat": "IWAD", "Type": "DOOM"},
    "id1.wad":          {"Name": "Doom II: Legacy of Rust", "IWAD": "doom2.wad", "Kat": "IWAD", "Type": "DOOM"},
}

GAME_PROFILE_MAPPING = {
    "doom": ("doom.wad", "DOOM", "PWAD"),
    "doom2": ("doom2.wad", "DOOM", "PWAD"),
    "heretic": ("heretic.wad", "HERETIC", "EXTRA"),
    "hexen": ("hexen.wad", "HEXEN", "EXTRA"),
}


def _read_text_file_safe(txt_path):
    """Liest TXT robust mit mehreren Encodings."""
    encodings = ("utf-8", "utf-8-sig", "cp1252", "latin-1")
    for enc in encodings:
        try:
            with open(txt_path, "r", encoding=enc, errors="ignore") as f:
                return f.read().lower()
        except Exception:
            continue
    return ""


def _detect_game_from_txt(target_dir):
    """Versucht das benötigte Hauptspiel aus TXT-Dateien zu erkennen."""
    try:
        txt_files = []
        for root, _, files in os.walk(target_dir):
            for fname in files:
                if fname.lower().endswith(".txt"):
                    txt_files.append(os.path.join(root, fname))

        if not txt_files:
            return None

        scores = {"doom": 0, "doom2": 0, "heretic": 0, "hexen": 0}

        for txt_path in txt_files:
            content = _read_text_file_safe(txt_path)
            if not content:
                continue

            # Eindeutige Treffer priorisieren
            if "heretic" in content:
                scores["heretic"] += 3
            if "hexen" in content or "hexdd" in content:
                scores["hexen"] += 3

            # Doom 2 / Final Doom Hinweise
            if "doom ii" in content or "doom 2" in content or "doom2" in content:
                scores["doom2"] += 3
            if "plutonia" in content or "tnt" in content:
                scores["doom2"] += 2

            # Ultimate Doom Hinweise
            if "ultimate doom" in content:
                scores["doom"] += 3

            # Generischer Doom Hinweis (niedriger gewichtet)
            if "doom" in content:
                scores["doom"] += 1

        best_game = max(scores, key=scores.get)
        return best_game if scores[best_game] > 0 else None
    except Exception:
        return None

@tracker
def install_custom(file_path, callback=None, resolve_game=None):
    """Installiert Dateien und sortiert Offizielle in IWAD, den Rest in PWAD."""
    def log(msg):
        if callback: callback(msg)
        else: print(f"[INSTALLER] {msg}")

    try:
        fname = os.path.basename(file_path).lower()
        base_name = os.path.splitext(fname)[0]
        
        # 1. PRÜFEN: Ist es eine offizielle Datei aus der Matrix?
        if fname in OFFICIAL_MAPPING:
            data = OFFICIAL_MAPPING[fname]
            title = data["Name"]
            iwad = data["IWAD"]
            kat = data["Kat"]
            prefix = data.get("Type", "DOOM")
            
            # ZIEL: Direkt in den IWAD-Ordner (KEIN UNTERORDNER)
            target_dir = cfg.IWAD_DIR
            folder_name = "-" 
            dest_path = os.path.join(target_dir, fname)
            
            log(f"› Verschiebe IWAD/Addon '{title}' in den IWAD-Ordner...")
            shutil.copy2(file_path, dest_path)
            
        else:
            # 2. PWAD / CUSTOM MAP (UNBEKANNT)
            title = base_name.replace("_", " ")
            folder_name = base_name
            target_dir = os.path.join(cfg.PWAD_DIR, folder_name)
            os.makedirs(target_dir, exist_ok=True)
            
            iwad, prefix, kat = "doom2.wad", "DOOM", "PWAD"
            
            log(f"› Installiere PWAD '{title}' in PWAD-Ordner...")
            
            if file_path.lower().endswith(".zip"):
                with zipfile.ZipFile(file_path, 'r') as z:
                    z.extractall(target_dir)
            else:
                shutil.copy2(file_path, os.path.join(target_dir, fname))

            # Erst TXT-Analyse nutzen (falls vorhanden)
            detected_game = _detect_game_from_txt(target_dir)

            # Danach Fallback auf Dateinamen-Hinweise
            for f in os.listdir(target_dir):
                fl = f.lower()
                if "heretic" in fl:
                    detected_game = "heretic"
                    break
                if "hexen" in fl:
                    detected_game = "hexen"
                    break

            # Wenn weiterhin unbekannt: Benutzer fragen (GUI-Callback)
            if not detected_game and callable(resolve_game):
                detected_game = resolve_game(file_path)

            if detected_game in GAME_PROFILE_MAPPING:
                iwad, prefix, kat = GAME_PROFILE_MAPPING[detected_game]
            elif not detected_game:
                log(f"⚠ Keine IWAD-Info gefunden für '{fname}'. Übersprungen.")
                return False

        # 3. DB-EINTRAG
        new_id = db.get_next_id(prefix=prefix)
        map_data = {
            "Cleared": "0",
            "NoMods": "0",
            "ID": new_id,
            "Name": title,
            "IWAD": iwad,
            "Path": folder_name,
            "MOD": "0",
            "ARGS": "0",
            "Kategorie": kat,
            "Playtime": "0",
            "LastPlayed": "-",
            "RemoteID": "0",
            "Favorite": "0"
        }
        
        if db.insert_map(map_data):
            return True
        else:
            log(f"❌ Fehler beim Einfügen in Datenbank: {new_id}")
            return False
    except Exception as e:
        log(f"❌ Fehler bei {file_path}: {e}")
        return False

def install_from_folder(callback=None, resolve_game=None):
    """Scannt 'Install'-Ordner und räumt ihn danach auf."""
    install_dir = os.path.join(cfg.BASE_DIR, "Install")
    if not os.path.exists(install_dir):
        os.makedirs(install_dir)
        return 0

    files = [f for f in os.listdir(install_dir) if f.lower().endswith((".wad", ".zip", ".pk3", ".pk7"))]
    count = 0
    
    for f in files:
        full_path = os.path.join(install_dir, f)
        if install_custom(full_path, callback, resolve_game=resolve_game):
            count += 1
            try:
                os.remove(full_path) # Datei nach Erfolg löschen
            except:
                pass

    if count > 0:
        db.repair_map_indices()
    return count