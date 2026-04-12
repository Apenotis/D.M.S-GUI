import configparser
import ctypes
import json
import os
import shutil
import time
import urllib.request
import urllib.error
import zipfile
from datetime import datetime

import dms_core.config as cfg


def _http_get_json(url: str, timeout: int = 15, retries: int = 3) -> dict:
    """Holt JSON robust mit Retry bei temporären HTTP-/Netzwerkfehlern."""
    headers = {
        "User-Agent": "DMS-EngineManager/3.1",
        "Accept": "application/vnd.github+json",
    }

    last_error = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as e:
            last_error = e
            # Bei 4xx außer 429 bringt Retry meist nichts.
            if 400 <= e.code < 500 and e.code != 429:
                break
        except Exception as e:
            last_error = e

        if attempt < retries:
            time.sleep(1.5 * attempt)

    raise RuntimeError(f"HTTP/JSON fehlgeschlagen: {last_error}")


def _get_release_data(repo: str) -> dict:
    """Holt Release-Daten, mit Fallback falls /latest nicht verfuegbar ist."""
    latest_url = f"https://api.github.com/repos/{repo}/releases/latest"
    try:
        return _http_get_json(latest_url, timeout=15, retries=3)
    except Exception:
        releases_url = f"https://api.github.com/repos/{repo}/releases"
        data = _http_get_json(releases_url, timeout=15, retries=3)
        if isinstance(data, list) and data:
            return data[0]
        raise RuntimeError("Keine Releases verfuegbar.")


def _download_file(url: str, target_file: str, timeout: int = 30, retries: int = 3):
    """Lädt Datei robust mit Retry und atomarem Dateischreiben."""
    headers = {
        "User-Agent": "DMS-EngineManager/3.1",
    }
    tmp_file = f"{target_file}.part"

    last_error = None
    for attempt in range(1, retries + 1):
        try:
            if os.path.exists(tmp_file):
                os.remove(tmp_file)

            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as response, open(tmp_file, "wb") as out_file:
                shutil.copyfileobj(response, out_file)

            os.replace(tmp_file, target_file)
            return
        except Exception as e:
            last_error = e
            if os.path.exists(tmp_file):
                try:
                    os.remove(tmp_file)
                except Exception:
                    pass
            if attempt < retries:
                time.sleep(2 * attempt)

    raise RuntimeError(f"Download fehlgeschlagen: {last_error}")

# ============================================================================
# ENGINE-MANAGEMENT (Pfade, Versionen, Downloads)
# ============================================================================

def get_engine_path(engine_name: str = None) -> str:
    """Liefert den effektiven EXE-Pfad (Custom-Pfad oder Standard unter Engines/)."""
    # Wir nehmen den Namen, oder den Wert aus der Config. 
    # Wenn beides leer ist, nehmen wir "" (statt 'GZDoom').
    eng = engine_name if engine_name else (cfg.CURRENT_ENGINE if cfg.CURRENT_ENGINE else "")
    
    if not eng:
        return "" # Wichtig: Wenn keine Engine gewählt ist, gibt es keinen Pfad

    eng_lower = eng.lower()

    # 1. Config laden
    config = configparser.ConfigParser()
    config.read(cfg.CONFIG_FILE, encoding="utf-8-sig") 

    # Falls du die ENGINES Sektion behalten willst (für Custom Pfade):
    if config.has_section("ENGINES"):
        custom_path = config.get("ENGINES", eng_lower, fallback="")
        if custom_path and os.path.exists(custom_path):
            return custom_path

    # 2. Standard-Automatik im Engines-Ordner:
    exe_name = f"{eng}.exe"
    path = os.path.join(cfg.ENGINE_BASE_DIR, eng, exe_name)
    
    return path

def get_engine_version(engine_path: str) -> str:
    """
    Ermittelt die Version der Engine aus den Windows-Datei-Metadaten.
    Fällt auf das Änderungsdatum zurück, wenn keine Metadaten gefunden werden.
    """
    if not engine_path or not os.path.exists(engine_path):
        return "N/A"

    try:
        filename = os.path.abspath(engine_path)
        size = ctypes.windll.version.GetFileVersionInfoSizeW(filename, None)
        if size <= 0:
            return "Bereit"

        res = ctypes.create_string_buffer(size)
        ctypes.windll.version.GetFileVersionInfoW(filename, None, size, res)
        fixed_info = ctypes.POINTER(ctypes.c_uint16)()
        fixed_size = ctypes.c_uint()

        if ctypes.windll.version.VerQueryValueW(
            res, "\\", ctypes.byref(fixed_info), ctypes.byref(fixed_size)
        ):
            if fixed_size.value:
                # Version aus den Datei-Informationen extrahieren
                major, minor, build = fixed_info[9], fixed_info[8], fixed_info[11]
                return f"{major}.{minor}.{build}"

        # Fallback auf das Änderungsdatum
        mtime = os.path.getmtime(engine_path)
        return datetime.fromtimestamp(mtime).strftime("%d.%m.%y")
    except Exception:
        return "Aktiv"

def get_all_engines_status() -> list:
    """
    Gibt eine Liste aller Engines und deren Status zurück.
    Diese Funktion ersetzt das alte CLI-Menü und füttert stattdessen die GUI.
    """
    status_list = []
    for eng in cfg.SUPPORTED_ENGINES:
        path = get_engine_path(eng)
        is_installed = os.path.exists(path)
        version = get_engine_version(path) if is_installed else "N/A"
        
        status_list.append({
            "name": eng,
            "installed": is_installed,
            "path": path,
            "version": version
        })
    return status_list

def install_engine(engine_name: str, callback=None) -> bool:
    """
    Lädt die gewählte Engine herunter und entpackt sie.
    Gibt True bei Erfolg, False bei Fehler zurück.
    Das 'callback' wird genutzt, um Status-Texte an die GUI zu senden.
    """
    def log(msg):
        if callback: callback(msg)
        else: print(f"[ENGINE MANAGER] {msg}")

    log(f"Bereite Download für {engine_name} vor...")
    engine_name = str(engine_name).strip().lower()
    zip_path = os.path.join(cfg.BASE_DIR, f"{engine_name}_temp.zip")
    download_url = ""
    direct_downloads = getattr(cfg, "DIRECT_DOWNLOADS", {})

    # 1) Download-Quelle bestimmen (Direct-Link oder GitHub Release Asset)
    if engine_name in direct_downloads:
        download_url = str(direct_downloads[engine_name]).strip()
    elif engine_name in cfg.ENGINE_REPOS:
        repo = cfg.ENGINE_REPOS[engine_name]
        if not repo or repo.startswith("http://") or repo.startswith("https://"):
            log("Engine-Quelle ist keine GitHub-Repo-Angabe. Bitte DIRECT_DOWNLOADS konfigurieren.")
            return False

        api_url = f"https://api.github.com/repos/{repo}/releases/latest"
        try:
            data = _get_release_data(repo)
            assets = data.get("assets", [])

            # Prioritaet: Windows x64 ZIP, dann beliebiges Windows ZIP.
            preferred = []
            fallback = []
            for asset in assets:
                name = str(asset.get("name", "")).lower()
                if any(x in name for x in ["sources", "source", "dev", "debug", "pdb"]):
                    continue
                if not name.endswith(".zip"):
                    continue

                is_windows = any(x in name for x in ["win", "windows", "x64", "x86", "w64"])
                if not is_windows:
                    continue

                if any(x in name for x in ["x64", "win64", "w64"]):
                    preferred.append(asset)
                else:
                    fallback.append(asset)

            selected = preferred[0] if preferred else (fallback[0] if fallback else None)
            if selected:
                download_url = selected.get("browser_download_url", "")
                log(f"Version gefunden: {selected.get('name', 'Unbekannt')}")
            elif assets:
                log("Release gefunden, aber kein passendes Windows-ZIP-Asset.")
            else:
                log("Release gefunden, aber ohne Assets.")
        except Exception as e:
            log(f"API-Fehler (GitHub): {e}")
            return False

    # 2) ZIP laden, validieren, entpacken und EXE ggf. aus Unterordner hochziehen
    if download_url:
        try:
            log(f"Lade herunter: {download_url.split('/')[-1]}...")
            _download_file(download_url, zip_path, timeout=45, retries=3)

            if not zipfile.is_zipfile(zip_path):
                raise ValueError("Datei ist kein gültiges ZIP.")

            log("Entpacke Dateien...")
            target_dir = os.path.join(cfg.ENGINE_BASE_DIR, engine_name)
            os.makedirs(target_dir, exist_ok=True)
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(target_dir)

            if os.path.exists(zip_path):
                os.remove(zip_path)

            # Auto-Move (falls die EXE im ZIP in einem Unterordner lag)
            exe_to_find = f"{engine_name}.exe"
            for root, dirs, files in os.walk(target_dir):
                if exe_to_find in files:
                    for f in os.listdir(root):
                        src = os.path.join(root, f)
                        dst = os.path.join(target_dir, f)
                        if not os.path.exists(dst):
                            os.replace(src, dst)
                    break

            log(f"{engine_name.upper()} erfolgreich installiert!")
            return True

        except Exception as e:
            log(f"Fehler beim Download/Entpacken: {e}")
            if os.path.exists(zip_path):
                try: os.remove(zip_path)
                except: pass
            return False
    else:
        log("Keine passende Windows-ZIP gefunden. Moeglich: kein Binary-Release, API-Limit oder temporaerer Serverfehler.")
        return False