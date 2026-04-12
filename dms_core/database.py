import csv
import os
import shutil
import sqlite3
from datetime import datetime

import dms_core.config as cfg
from dms_core.utils import tracker

# Die finale Matrix mit 13 Spalten (Favorit ist die letzte)
HEADER = [
    "Cleared", "NoMods", "ID", "Name", "IWAD", "Path", 
    "MOD", "ARGS", "Kategorie", "Playtime", "LastPlayed", "RemoteID", "Favorite"
]

def get_db_connection():
    """Erstellt eine Verbindung zur SQLite-Datenbank."""
    return sqlite3.connect(cfg.DB_FILE)

def create_table_if_not_exists():
    """Erstellt die Tabelle, falls sie nicht existiert."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS maps (
            Cleared TEXT,
            NoMods TEXT,
            ID TEXT PRIMARY KEY,
            Name TEXT,
            IWAD TEXT,
            Path TEXT,
            MOD TEXT,
            ARGS TEXT,
            Kategorie TEXT,
            Playtime TEXT,
            LastPlayed TEXT,
            RemoteID TEXT,
            Favorite TEXT
        )
    ''')
    conn.commit()
    conn.close()

def migrate_from_csv():
    """Migriert Daten von CSV zu SQLite, falls CSV existiert und DB leer ist."""
    if not os.path.exists(cfg.CSV_FILE):
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM maps")
    if cursor.fetchone()[0] > 0:
        conn.close()
        return  # DB bereits gefüllt
    
    try:
        with open(cfg.CSV_FILE, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f, fieldnames=HEADER, delimiter=";")
            next(reader, None)  # Header überspringen
            for row in reader:
                if "RemoteID" not in row or row["RemoteID"] is None:
                    row["RemoteID"] = "0"
                if "Favorite" not in row or row["Favorite"] is None:
                    row["Favorite"] = "0"
                cursor.execute('''
                    INSERT OR IGNORE INTO maps 
                    (Cleared, NoMods, ID, Name, IWAD, Path, MOD, ARGS, Kategorie, Playtime, LastPlayed, RemoteID, Favorite)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    row.get("Cleared", "0"),
                    row.get("NoMods", "0"),
                    row.get("ID", ""),
                    row.get("Name", ""),
                    row.get("IWAD", ""),
                    row.get("Path", ""),
                    row.get("MOD", ""),
                    row.get("ARGS", ""),
                    row.get("Kategorie", ""),
                    row.get("Playtime", "0"),
                    row.get("LastPlayed", ""),
                    row.get("RemoteID", "0"),
                    row.get("Favorite", "0")
                ))
        conn.commit()
        print("✅ Migration von CSV zu SQLite abgeschlossen.")
    except Exception as e:
        print(f"❌ Fehler bei Migration: {e}")
    finally:
        conn.close()

# Initialisierung
create_table_if_not_exists()
migrate_from_csv()

@tracker
def get_all_maps():
    """Liest alle Maps aus der SQLite-Datenbank."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM maps ORDER BY ID")
    rows = cursor.fetchall()
    conn.close()
    
    maps = []
    for row in rows:
        maps.append(dict(zip(HEADER, row)))
    return maps

def get_map_by_id(map_id):
    """Sucht eine Karte anhand ihrer ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM maps WHERE ID = ? LIMIT 1", (str(map_id).strip().upper(),))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return dict(zip(HEADER, row))
    return None

@tracker
def save_all_maps(maps):
    """Speichert die Liste der Maps in die Datenbank (ersetzt alle)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM maps")
        for m in maps:
            cursor.execute('''
                INSERT INTO maps 
                (Cleared, NoMods, ID, Name, IWAD, Path, MOD, ARGS, Kategorie, Playtime, LastPlayed, RemoteID, Favorite)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                m.get("Cleared", "0"),
                m.get("NoMods", "0"),
                m.get("ID", ""),
                m.get("Name", ""),
                m.get("IWAD", ""),
                m.get("Path", ""),
                m.get("MOD", ""),
                m.get("ARGS", ""),
                m.get("Kategorie", ""),
                m.get("Playtime", "0"),
                m.get("LastPlayed", ""),
                m.get("RemoteID", "0"),
                m.get("Favorite", "0")
            ))
        conn.commit()
        return True
    except Exception as e:
        print(f"❌ DB Speicher-Fehler: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

# ============================================================================
# STATUS-FUNKTIONEN (FIX FÜR RECHTSKLICK-MENÜ)
# ============================================================================

def toggle_map_clear(map_id):
    """Schaltet den 'Cleared' Status um."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE maps SET Cleared = CASE WHEN Cleared = '0' THEN '1' ELSE '0' END WHERE ID = ?", (str(map_id).strip().upper(),))
        conn.commit()
        return True
    except Exception as e:
        print(f"❌ Fehler beim Umschalten Cleared: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def toggle_mod_skip(map_id):
    """Schaltet den 'NoMods' Status um."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE maps SET NoMods = CASE WHEN NoMods = '0' THEN '1' ELSE '0' END WHERE ID = ?", (str(map_id).strip().upper(),))
        conn.commit()
        return True
    except Exception as e:
        print(f"❌ Fehler beim Umschalten NoMods: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def toggle_favorite(map_id):
    """Schaltet den Favoriten-Status um."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE maps SET Favorite = CASE WHEN Favorite = '0' THEN '1' ELSE '0' END WHERE ID = ?", (str(map_id).strip().upper(),))
        conn.commit()
        return True
    except Exception as e:
        print(f"❌ Fehler beim Umschalten Favorite: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def update_map_name(map_id, new_name):
    """Aktualisiert den Namen einer Map."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        clean_id = str(map_id).strip().upper()
        clean_name = str(new_name).strip()
        if not clean_id or not clean_name:
            return False

        cursor.execute("UPDATE maps SET Name = ? WHERE ID = ?", (clean_name, clean_id))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        print(f"❌ Fehler beim Umbenennen: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def update_map_args(map_id, new_args):
    """Aktualisiert die Startparameter (ARGS) einer Map."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        clean_id = str(map_id).strip().upper()
        clean_args = str(new_args).strip() if new_args is not None else "0"
        if not clean_id:
            return False

        # Leere Eingabe als '0' speichern (entspricht: keine Zusatzparameter)
        if clean_args == "":
            clean_args = "0"

        cursor.execute("UPDATE maps SET ARGS = ? WHERE ID = ?", (clean_args, clean_id))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        print(f"❌ Fehler beim ARGS-Update: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

# ============================================================================
# SPIELZEIT & STATISTIK
# ============================================================================

def get_total_seconds():
    """Liest die Gesamtspielzeit aus der config.ini (Sektion [STATS])."""
    try:
        return int(cfg.config.get("STATS", "totaltime", fallback="0"))
    except Exception as e:
        print(f"⚠️ Fehler beim Lesen der Spielzeit aus INI: {e}")
        return 0

def save_total_seconds(seconds):
    """Speichert die Spielzeit in die config.ini."""
    try:
        cfg.set_stat("TotalTime", int(seconds))
        return True
    except Exception as e:
        print(f"❌ Fehler beim Speichern der Spielzeit: {e}")
        return False

# ============================================================================
# ADMIN & REPARATUR
# ============================================================================

def get_next_id(prefix="DOOM"):
    """Generiert die nächste freie ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT ID FROM maps WHERE ID LIKE ?", (f"{prefix}%",))
    ids = cursor.fetchall()
    conn.close()
    
    max_num = 0
    for (mid,) in ids:
        if mid.startswith(prefix):
            try:
                num = int(mid.replace(prefix, ""))
                if num > max_num:
                    max_num = num
            except:
                continue
    return f"{prefix}{max_num + 1}"

@tracker
def repair_map_indices():
    """Sortiert die Datenbank sauber nach IDs (nicht nötig in SQLite, aber behalten für Kompatibilität)."""
    # In SQLite ist die Reihenfolge durch ORDER BY garantiert
    return True

def delete_map(map_id):
    """Löscht eine Map aus der Datenbank und von der Festplatte."""
    map_data = get_map_by_id(map_id)
    if map_data:
        map_path = str(map_data.get("Path", "")).strip()
        if map_path and map_path != "-":
            full_path = os.path.join(cfg.PWAD_DIR, map_path)
            try:
                if os.path.exists(full_path):
                    if os.path.isdir(full_path):
                        shutil.rmtree(full_path)
                    else:
                        os.remove(full_path)
            except:
                pass
        
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM maps WHERE ID = ?", (str(map_id).strip().upper(),))
            conn.commit()
            return True
        except Exception as e:
            print(f"❌ Fehler beim Löschen: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    return False

def insert_map(map_data):
    """Fügt eine neue Map in die Datenbank ein."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO maps 
            (Cleared, NoMods, ID, Name, IWAD, Path, MOD, ARGS, Kategorie, Playtime, LastPlayed, RemoteID, Favorite)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            map_data.get("Cleared", "0"),
            map_data.get("NoMods", "0"),
            map_data.get("ID", ""),
            map_data.get("Name", ""),
            map_data.get("IWAD", ""),
            map_data.get("Path", ""),
            map_data.get("MOD", ""),
            map_data.get("ARGS", ""),
            map_data.get("Kategorie", ""),
            map_data.get("Playtime", "0"),
            map_data.get("LastPlayed", ""),
            map_data.get("RemoteID", "0"),
            map_data.get("Favorite", "0")
        ))
        conn.commit()
        return True
    except Exception as e:
        print(f"❌ Fehler beim Einfügen: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def uninstall_map(map_id):
    """Kompatibilitaets-Alias fuer bestehende GUI-Aufrufe."""
    return delete_map(map_id)