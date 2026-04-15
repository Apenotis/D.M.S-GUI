import csv
import os
import shutil
import zipfile

import dms_core.config as cfg
import dms_core.database as db
from dms_core.utils import tracker

# ============================================================================
# Official file mapping (IWAD)
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

INSTALL_EXTENSIONS = (".wad", ".zip", ".pk3", ".pk7")


def _read_text_file_safe(txt_path):
    """Read a TXT file robustly using multiple encodings."""
    encodings = ("utf-8", "utf-8-sig", "cp1252", "latin-1")
    for enc in encodings:
        try:
            with open(txt_path, "r", encoding=enc, errors="ignore") as f:
                return f.read().lower()
        except Exception:
            continue
    return ""


def _detect_game_from_txt(target_dir):
    """Try to detect the required base game from TXT files."""
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

            # Prioritize explicit matches.
            if "heretic" in content:
                scores["heretic"] += 3
            if "hexen" in content or "hexdd" in content:
                scores["hexen"] += 3

            # Hints for Doom II / Final Doom.
            if "doom ii" in content or "doom 2" in content or "doom2" in content:
                scores["doom2"] += 3
            if "plutonia" in content or "tnt" in content:
                scores["doom2"] += 2

            # Hints for Ultimate Doom.
            if "ultimate doom" in content:
                scores["doom"] += 3

            # Generic Doom hint with lower priority.
            if "doom" in content:
                scores["doom"] += 1

        best_game = max(scores, key=scores.get)
        return best_game if scores[best_game] > 0 else None
    except Exception:
        return None

@tracker
def install_custom(file_path, callback=None, resolve_game=None):
    """Install files and sort official content into IWAD, everything else into PWAD."""
    def log(msg):
        if callback: callback(msg)
        else: print(f"[INSTALLER] {msg}")

    try:
        fname = os.path.basename(file_path).lower()
        base_name = os.path.splitext(fname)[0]
        
        # Check for official files.
        if fname in OFFICIAL_MAPPING:
            data = OFFICIAL_MAPPING[fname]
            title = data["Name"]
            iwad = data["IWAD"]
            kat = data["Kat"]
            prefix = data.get("Type", "DOOM")
            
            # Target: copy directly into the IWAD directory.
            target_dir = cfg.IWAD_DIR
            folder_name = "-" 
            dest_path = os.path.join(target_dir, fname)
            
            log(f"> Moving IWAD/add-on '{title}' into the IWAD directory...")
            shutil.copy2(file_path, dest_path)
            
        else:
            # Handle PWAD/custom map content.
            title = base_name.replace("_", " ")
            folder_name = base_name
            target_dir = os.path.join(cfg.PWAD_DIR, folder_name)
            os.makedirs(target_dir, exist_ok=True)
            
            iwad, prefix, kat = "doom2.wad", "DOOM", "PWAD"
            
            log(f"> Installing PWAD '{title}' into the PWAD directory...")
            
            if file_path.lower().endswith(".zip"):
                with zipfile.ZipFile(file_path, 'r') as z:
                    z.extractall(target_dir)
            else:
                shutil.copy2(file_path, os.path.join(target_dir, fname))

            # First try TXT-based analysis.
            detected_game = _detect_game_from_txt(target_dir)

            # Then fall back to filename heuristics.
            for f in os.listdir(target_dir):
                fl = f.lower()
                if "heretic" in fl:
                    detected_game = "heretic"
                    break
                if "hexen" in fl:
                    detected_game = "hexen"
                    break

            # If still unclear, use the user callback.
            if not detected_game and callable(resolve_game):
                detected_game = resolve_game(file_path)

            if detected_game in GAME_PROFILE_MAPPING:
                iwad, prefix, kat = GAME_PROFILE_MAPPING[detected_game]
            elif not detected_game:
                log(f"Warning: no IWAD info found for '{fname}'. Skipped.")
                return False

            # Create the database entry.
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
            log(f"Error inserting into database: {new_id}")
            return False
    except Exception as e:
        log(f"Error while processing {file_path}: {e}")
        return False

def install_from_folder(callback=None, resolve_game=None):
    """Scan the Install folder and clean it up afterwards."""
    install_dir = os.path.join(cfg.BASE_DIR, "Install")
    files = get_install_candidates(install_dir)
    count = 0
    
    for full_path in files:
        if install_custom(full_path, callback, resolve_game=resolve_game):
            count += 1
            try:
                os.remove(full_path)
            except:
                pass

    if count > 0:
        db.repair_map_indices()
    return count


def get_install_candidates(install_dir=None):
    """Return full paths of importable files from Install/."""
    target_dir = install_dir or os.path.join(cfg.BASE_DIR, "Install")
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)
        return []

    candidates = []
    for fname in os.listdir(target_dir):
        if fname.lower().endswith(INSTALL_EXTENSIONS):
            candidates.append(os.path.join(target_dir, fname))
    return sorted(candidates)