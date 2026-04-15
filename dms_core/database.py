import csv
import os
import shutil
import sqlite3
from datetime import datetime

import dms_core.config as cfg
from dms_core.utils import tracker

# Final 13-column schema (Favorite is the last column)
HEADER = [
    "Cleared", "NoMods", "ID", "Name", "IWAD", "Path", 
    "MOD", "ARGS", "Kategorie", "Playtime", "LastPlayed", "RemoteID", "Favorite"
]

def get_db_connection():
    """Create a connection to the SQLite database."""
    return sqlite3.connect(cfg.DB_FILE)

def create_table_if_not_exists():
    """Create the table if it does not exist yet."""
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
    """Migrate data from CSV to SQLite if the CSV exists and the DB is empty."""
    if not os.path.exists(cfg.CSV_FILE):
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM maps")
    if cursor.fetchone()[0] > 0:
        conn.close()
        return  # DB already populated
    
    try:
        with open(cfg.CSV_FILE, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f, fieldnames=HEADER, delimiter=";")
            next(reader, None)  # Skip header
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
        print("CSV to SQLite migration completed.")
    except Exception as e:
        print(f"Migration error: {e}")
    finally:
        conn.close()

# Initialization
create_table_if_not_exists()
migrate_from_csv()

@tracker
def get_all_maps():
    """Read all maps from the SQLite database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    # Preserve insertion order so new maps appear at the end.
    cursor.execute("SELECT * FROM maps ORDER BY ROWID ASC")
    rows = cursor.fetchall()
    conn.close()
    
    maps = []
    for row in rows:
        maps.append(dict(zip(HEADER, row)))
    return maps

def get_map_by_id(map_id):
    """Look up a map by its ID."""
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
    """Save the full map list to the database, replacing existing rows."""
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
        print(f"DB save error: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

# ============================================================================
# Status functions
# ============================================================================

def toggle_map_clear(map_id):
    """Toggle the Cleared status."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE maps SET Cleared = CASE WHEN Cleared = '0' THEN '1' ELSE '0' END WHERE ID = ?", (str(map_id).strip().upper(),))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error toggling Cleared: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def toggle_mod_skip(map_id):
    """Toggle the NoMods status."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE maps SET NoMods = CASE WHEN NoMods = '0' THEN '1' ELSE '0' END WHERE ID = ?", (str(map_id).strip().upper(),))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error toggling NoMods: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def toggle_favorite(map_id):
    """Toggle favorite status."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE maps SET Favorite = CASE WHEN Favorite = '0' THEN '1' ELSE '0' END WHERE ID = ?", (str(map_id).strip().upper(),))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error toggling Favorite: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def update_map_name(map_id, new_name):
    """Update a map name."""
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
        print(f"Rename error: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def update_map_args(map_id, new_args):
    """Update a map's launch arguments (ARGS)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        clean_id = str(map_id).strip().upper()
        clean_args = str(new_args).strip() if new_args is not None else "0"
        if not clean_id:
            return False

        # Store empty input as '0' to represent no extra arguments.
        if clean_args == "":
            clean_args = "0"

        cursor.execute("UPDATE maps SET ARGS = ? WHERE ID = ?", (clean_args, clean_id))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        print(f"ARGS update error: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

# ============================================================================
# Playtime and stats
# ============================================================================

def get_total_seconds():
    """Read total playtime from config.ini ([STATS])."""
    try:
        return int(cfg.config.get("STATS", "totaltime", fallback="0"))
    except Exception as e:
        print(f"Warning reading playtime from INI: {e}")
        return 0

def save_total_seconds(seconds):
    """Save playtime to config.ini."""
    try:
        cfg.set_stat("TotalTime", int(seconds))
        return True
    except Exception as e:
        print(f"Error saving playtime: {e}")
        return False

# ============================================================================
# Admin and repair
# ============================================================================

def get_next_id(prefix="DOOM"):
    """Generate the next free ID."""
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
    """Compatibility stub for index repair after the SQLite migration."""
    # SQLite ordering is controlled via ORDER BY.
    return True

def delete_map(map_id):
    """Delete a map from the database and disk."""
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
            print(f"Delete error: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    return False

def find_duplicates(iwad_filename, path):
    """Return existing DB rows that match the same IWAD entry or PWAD path.

    For official IWADs (path == '-') the lookup is done by IWAD filename.
    For PWADs the lookup is done by folder path.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if path and path != "-":
            cursor.execute("SELECT * FROM maps WHERE Path = ?", (path,))
        else:
            cursor.execute("SELECT * FROM maps WHERE IWAD = ? AND Path = '-'", (iwad_filename,))
        rows = cursor.fetchall()
        return [dict(zip(HEADER, r)) for r in rows]
    finally:
        conn.close()


def insert_map(map_data):
    """Insert a new map into the database."""
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
        print(f"Insert error: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def uninstall_map(map_id):
    """Compatibility alias for existing GUI calls."""
    return delete_map(map_id)