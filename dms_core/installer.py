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

@tracker
def install_custom(file_path, callback=None):
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

            # Engine-Check für PWADs
            for f in os.listdir(target_dir):
                if "heretic" in f.lower(): iwad, prefix, kat = "heretic.wad", "HERETIC", "EXTRA"
                elif "hexen" in f.lower(): iwad, prefix, kat = "hexen.wad", "HEXEN", "EXTRA"

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

def install_from_folder(callback=None):
    """Scannt 'Install'-Ordner und räumt ihn danach auf."""
    install_dir = os.path.join(cfg.BASE_DIR, "Install")
    if not os.path.exists(install_dir):
        os.makedirs(install_dir)
        return 0

    files = [f for f in os.listdir(install_dir) if f.lower().endswith((".wad", ".zip", ".pk3"))]
    count = 0
    
    for f in files:
        full_path = os.path.join(install_dir, f)
        if install_custom(full_path, callback):
            count += 1
            try:
                os.remove(full_path) # Datei nach Erfolg löschen
            except:
                pass

    if count > 0:
        db.repair_map_indices()
    return count