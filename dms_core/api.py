import csv
import json
import os
import shutil
import ssl
import traceback
import urllib.parse
import urllib.request
import zipfile

import dms_core.config as cfg
import dms_core.database as db
from dms_core.utils import tracker

# ============================================================================
# Detection of installed maps
# ============================================================================

def get_installed_info() -> dict:
    """Fetch RemoteIDs and names from the DB for comparison."""
    info = {"ids": [], "names": []}
    try:
        maps = db.get_all_maps()
        for m in maps:
            # 1. Doomworld ID (12th column)
            r_id = str(m.get("RemoteID", "0")).strip()
            if r_id != "0": 
                info["ids"].append(r_id)
            
            # 2. Path and name (for older maps without an ID)
            path = str(m.get("Path", "")).lower().replace("_", "").replace("-", "")
            name = str(m.get("Name", "")).lower().replace(" ", "")
            if path and path != "-": info["names"].append(path)
            if name: info["names"].append(name)
    except: pass
    return info

# ============================================================================
# Doomworld API interaction
# ============================================================================

def fetch_api_content(folder_path):
    url = f"https://www.doomworld.com/idgames/api/api.php?action=getcontents&name={urllib.parse.quote(folder_path)}&out=json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        ctx = ssl._create_unverified_context()
        with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8-sig"))
            content = data.get("content", {})
            
            # Extract files
            f = content.get("file", [])
            files = [f] if isinstance(f, dict) else (f or [])
            
            # Extract subdirectories
            d = content.get("dir", [])
            dirs = [d] if isinstance(d, dict) else (d or [])
            
            return files, dirs
    except:
        return [], []

def get_top_wads(category: str, callback=None) -> list:
    """Fetch top lists without duplicates by tracking IDs."""
    def log(msg):
        if callback: callback(msg)

    path_map = {
        "doom_megawads":  ["levels/doom/megawads/"],
        "doom2_megawads": ["levels/doom2/megawads/", "levels/doom2/Ports/megawads/"],
        "heretic":        ["levels/heretic/", "levels/heretic/Ports/"],
        "hexen":          ["levels/hexen/", "levels/hexen/Ports/"]
    }

    main_folders = path_map.get(category, [])
    if not main_folders:
        return []

    all_results = []
    seen_ids = set()  # Track IDs to avoid duplicates.
    db_info = get_installed_info()

    log(f"Syncing {category}...")

    for main_folder in main_folders:
        # 1. Load files from the main folder
        files, subdirs = fetch_api_content(main_folder)
        
        for f in files:
            f_id = str(f.get("id", ""))
            if f_id and f_id not in seen_ids:
                all_results.append(f)
                seen_ids.add(f_id)
            
        # 2. Scan subdirectories
        if subdirs:
            for sd in subdirs:
                folder_name = str(sd.get("name", "")).lower()
                
                # Apply category filters
                if any(x in folder_name for x in ["deathmatch", "music", "skins", "sounds"]):
                    continue
                
                # Skip paths already covered by a main folder.
                # This avoids scanning entries such as 'heretic/Ports' twice.
                if any(folder_name.startswith(p.lower()) for p in main_folders if p.lower() != main_folder.lower()):
                    continue

                s_files, _ = fetch_api_content(folder_name)
                for f in s_files:
                    f_id = str(f.get("id", ""))
                    if f_id and f_id not in seen_ids:
                        all_results.append(f)
                        seen_ids.add(f_id)

    # 3. Sort and mark installation status
    all_results.sort(key=lambda x: float(x.get("rating", 0) or 0), reverse=True)

    for res in all_results:
        f_id = str(res.get("id", ""))
        fname = str(res.get("filename", "")).lower().split("/")[-1]
        clean_name = os.path.splitext(fname)[0].replace("_", "").replace("-", "")
        res["is_installed"] = (f_id in db_info.get("ids", []) or clean_name in db_info.get("names", []))

    log(f"Done: {len(all_results)} maps (duplicates removed).")
    return all_results

def search_idgames(query: str) -> list:
    """Search maps and mark results that are already installed."""
    db_info = get_installed_info()
    url = f"https://www.doomworld.com/idgames/api/api.php?action=search&query={urllib.parse.quote(query)}&type=title&sort=rating&dir=desc&out=json"
    
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        ctx = ssl._create_unverified_context()
        with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8-sig"))
            res = data.get("content", {}).get("file", [])
            results = [res] if isinstance(res, dict) else (res or [])
            
            for f in results:
                f_id = str(f.get("id", ""))
                fname = f.get("filename", "").split("/")[-1].lower()
                clean_name = os.path.splitext(fname)[0].replace("_", "").replace("-", "")
                title_clean = str(f.get("title", "")).lower().replace(" ", "")
                
                f["is_installed"] = (f_id in db_info["ids"] or 
                                     clean_name in db_info["names"] or 
                                     title_clean in db_info["names"])
            return results
    except Exception as e:
        print(f"[API ERROR] Search: {e}")
        return []

@tracker
def download_idgames_gui(file_obj: dict, callback=None):
    """Download a map, extract it, and register it in the database."""
    def log(msg):
        if callback: callback(msg)
        else: print(f"[API] {msg}")

    try:
        dl_dir = file_obj.get("dir", "").strip("/")
        filename = file_obj.get("filename", "").lstrip("/")
        file_id = str(file_obj.get("id", "0"))
        title = str(file_obj.get("title", filename)).replace(";", "-")

        # Mirror URL plus browser-like headers
        url = f"https://youfailit.net/pub/idgames/{dl_dir}/{filename}"
        log(f"Downloading: {title}...")
        
        zip_path = os.path.join(cfg.BASE_DIR, "Install", filename)
        os.makedirs(os.path.dirname(zip_path), exist_ok=True)

        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        ctx = ssl._create_unverified_context()
        with urllib.request.urlopen(req, context=ctx, timeout=25) as resp, open(zip_path, 'wb') as out:
            shutil.copyfileobj(resp, out)

        log("Extracting...")
        folder_name = title.replace(" ", "_").replace(":", "").replace("/", "")
        extract_path = os.path.join(cfg.PWAD_DIR, folder_name)
        os.makedirs(extract_path, exist_ok=True)
        with zipfile.ZipFile(zip_path, 'r') as z:
            z.extractall(extract_path)
        os.remove(zip_path)

        # Categorization
        analysis = f"{dl_dir.lower()} {str(file_obj.get('description','')).lower()} {title.lower()}"
        if "hexen" in analysis: iwad, g_type, cat = "hexen.wad", "HEXEN", "EXTRA"
        elif "heretic" in analysis: iwad, g_type, cat = "heretic.wad", "HERETIC", "EXTRA"
        elif "strife" in analysis: iwad, g_type, cat = "strife1.wad", "STRIFE", "EXTRA"
        elif "doom2" in analysis or "ports" in dl_dir.lower(): iwad, g_type, cat = "doom2.wad", "DOOM", "PWAD"
        else: iwad, g_type, cat = "doom.wad", "DOOM", "PWAD"

        # Database entry
        new_id = db.get_next_id(g_type)
        log(f"Registering: {new_id}...")
        map_data = {
            "Cleared": "0",
            "NoMods": "0",
            "ID": new_id,
            "Name": title,
            "IWAD": iwad,
            "Path": folder_name,
            "MOD": "0",
            "ARGS": "0",
            "Kategorie": cat,
            "Playtime": "0",
            "LastPlayed": "-",
            "RemoteID": file_id,
            "Favorite": "0"
        }
        
        if db.insert_map(map_data):
            db.repair_map_indices()
            log(f"Installed successfully: {title}.")
            return True, new_id
        else:
            return False, "Failed to insert into database"

    except Exception as e:
        log(f"Error: {e}")
        return False, str(e)