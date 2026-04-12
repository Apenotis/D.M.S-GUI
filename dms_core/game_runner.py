import os
import subprocess
from datetime import datetime

import dms_core.config as cfg
import dms_core.database as db
from dms_core.utils import tracker

VALID_EXTS = (".wad", ".pk3", ".pk7", ".zip", ".deh", ".bex", ".ipk3", ".pke", ".kpf")

@tracker
def get_start_command(engine_exe, map_data, selected_mods=None):
    """
    Baut den Startbefehl (CMD) für die Engine zusammen.
    Liest den Ordner der Map aus und sucht automatisch alle relevanten Dateien.
    """
    if selected_mods is None: 
        selected_mods = []

    # Wir lesen die Daten DIREKT aus dem map_data Dictionary (kein CSV-öffnen mehr!)
    core = str(map_data.get('IWAD', '')).strip()
    map_path = str(map_data.get('Path', '')).strip()
    kat = str(map_data.get('Kategorie', 'IWAD')).strip().upper()
    args = str(map_data.get('ARGS', '0')).strip()

    all_files_to_load = []

    # 1. PWADs / Custom Maps einbinden
    # Wenn es keine IWAD ist und ein Pfad in der Datenbank steht:
    if kat != "IWAD" and map_path and map_path != "-":
        full_map_path = os.path.join(cfg.PWAD_DIR, map_path)
        
        # Ist es eine direkte Datei? (z.B. mymap.wad)
        if os.path.isfile(full_map_path):
            all_files_to_load.append(full_map_path)
        
        # Ist es ein entpackter Ordner? (Wie NJ_Doom)
        elif os.path.isdir(full_map_path):
            for root, _, files in os.walk(full_map_path):
                for f in files:
                    if f.lower().endswith(VALID_EXTS):
                        all_files_to_load.append(os.path.join(root, f))

    # 2. Vom User im Menü ausgewählte Mods dranhängen
    for mod in selected_mods:
        mod_path = os.path.join(cfg.BASE_DIR, "mods", mod)
        
        if os.path.exists(mod_path):
            # Fall A: Es ist eine direkte Datei (z.B. Minimap.pk3)
            if os.path.isfile(mod_path):
                all_files_to_load.append(mod_path)
            
            # Fall B: Es ist ein Ordner (z.B. mods/doom/Minimap/)
            elif os.path.isdir(mod_path):
                # Wir durchsuchen den Ordner rekursiv nach allen Mod-Dateien
                for root, _, files in os.walk(mod_path):
                    for f in files:
                        if f.lower().endswith(VALID_EXTS):
                            full_path = os.path.join(root, f)
                            if full_path not in all_files_to_load:
                                all_files_to_load.append(full_path)
        else:
            # Fall C: Die Datei wurde ohne Endung übergeben (z.B. "Minimap" statt "Minimap.pk3")
            # Wir versuchen, die Datei mit einer der gültigen Endungen zu finden
            parent_dir = os.path.dirname(mod_path)
            base_name = os.path.basename(mod_path).lower()
            
            if os.path.exists(parent_dir):
                for f in os.listdir(parent_dir):
                    if f.lower().startswith(base_name) and f.lower().endswith(VALID_EXTS):
                        all_files_to_load.append(os.path.join(parent_dir, f))
                        break

    # 3. Den Befehl zusammenbauen
    cmd = [engine_exe, "-iwad", os.path.join(cfg.IWAD_DIR, core)]
    
    engine_dir = os.path.dirname(engine_exe)
    if any(x in engine_exe.lower() for x in ["gzdoom", "uzdoom", "lzdoom"]):
        cmd.extend(["+logfile", os.path.join(engine_dir, "logfile.txt")])

    # HIER PASSIERT DIE MAGIE: Der -file Parameter lädt alle Maps und Mods auf einmal!
    if all_files_to_load:
        cmd.append("-file")
        cmd.extend(all_files_to_load)

    # 4. Zusätzliche Custom-Parameter (ARGS) anhängen
    if args and args != "0" and args != "-":
        cmd.extend(args.split())

    return {
        "engine": engine_exe,
        "cmd": cmd,
        "engine_dir": engine_dir
    }

@tracker
def run_game(engine_exe, map_data, selected_mods=None):
    """Führt das Spiel aus und protokolliert die Spielzeit."""
    map_id = str(map_data.get('ID', '0')).strip()
    
    info = get_start_command(engine_exe, map_data, selected_mods)
    cmd = info["cmd"]
    engine_dir = info["engine_dir"]

    start_time = datetime.now()
    try:
        # Starte die Engine (blockiert, bis das Spiel beendet wird)
        subprocess.run(cmd, cwd=engine_dir, check=True)

        # Spielzeit berechnen
        end_time = datetime.now()
        played_seconds = int((end_time - start_time).total_seconds())
        played_minutes = max(1, played_seconds // 60)

        # Gesamtspielzeit (Dashboard) aktualisieren
        total_sec = db.get_total_seconds()
        db.save_total_seconds(total_sec + played_seconds)

        # Karte in der CSV aktualisieren (LastPlayed)
        if map_id and map_id != "0":
            # Datum für Last Played formatieren
            date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
            # Wir nutzen einen internen Fix, um Playtime und Datum zu setzen
            maps = db.get_all_maps()
            for m in maps:
                if str(m.get("ID", "")) == map_id:
                    try: old_time = int(m.get("Playtime", "0"))
                    except: old_time = 0
                    m["Playtime"] = str(old_time + played_minutes)
                    m["LastPlayed"] = date_str
                    db.save_all_maps(maps)
                    break

        return True

    except Exception as e:
        print(f"[RUNNER] Fehler beim Ausführen des Spiels: {e}")
        raise # Der Tracker schnappt sich den Fehler!