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
    """Fetch JSON robustly with retries for temporary HTTP/network errors."""
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
            # Retrying most 4xx responses except 429 usually does not help.
            if 400 <= e.code < 500 and e.code != 429:
                break
        except Exception as e:
            last_error = e

        if attempt < retries:
            time.sleep(1.5 * attempt)

    raise RuntimeError(f"HTTP/JSON request failed: {last_error}")


def _get_release_data(repo: str) -> dict:
    """Fetch release data with a fallback when /latest is unavailable."""
    latest_url = f"https://api.github.com/repos/{repo}/releases/latest"
    try:
        return _http_get_json(latest_url, timeout=15, retries=3)
    except Exception:
        releases_url = f"https://api.github.com/repos/{repo}/releases"
        data = _http_get_json(releases_url, timeout=15, retries=3)
        if isinstance(data, list) and data:
            return data[0]
        raise RuntimeError("No releases available.")


def _download_file(url: str, target_file: str, timeout: int = 30, retries: int = 3):
    """Download a file robustly with retries and atomic replacement."""
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

    raise RuntimeError(f"Download failed: {last_error}")

# ============================================================================
# Engine management
# ============================================================================

def get_engine_path(engine_name: str = None) -> str:
    """Return the effective EXE path (custom path or default under Engines/)."""
    # Use the explicit name or fall back to the current engine.
    eng = engine_name if engine_name else (cfg.CURRENT_ENGINE if cfg.CURRENT_ENGINE else "")
    
    if not eng:
        return ""

    eng_lower = eng.lower()

    # Load configuration.
    config = configparser.ConfigParser()
    config.read(cfg.CONFIG_FILE, encoding="utf-8-sig") 

    # Check the optional custom path.
    if config.has_section("ENGINES"):
        custom_path = config.get("ENGINES", eng_lower, fallback="")
        if custom_path and os.path.exists(custom_path):
            return custom_path

    # Default path inside the Engines directory.
    exe_name = f"{eng}.exe"
    path = os.path.join(cfg.ENGINE_BASE_DIR, eng, exe_name)
    
    return path

def get_engine_version(engine_path: str) -> str:
    """
    Read the engine version from Windows file metadata.
    Fall back to the file modification date when metadata is unavailable.
    """
    if not engine_path or not os.path.exists(engine_path):
        return "N/A"

    try:
        filename = os.path.abspath(engine_path)
        size = ctypes.windll.version.GetFileVersionInfoSizeW(filename, None)
        if size <= 0:
            return "Ready"

        res = ctypes.create_string_buffer(size)
        ctypes.windll.version.GetFileVersionInfoW(filename, None, size, res)
        fixed_info = ctypes.POINTER(ctypes.c_uint16)()
        fixed_size = ctypes.c_uint()

        if ctypes.windll.version.VerQueryValueW(
            res, "\\", ctypes.byref(fixed_info), ctypes.byref(fixed_size)
        ):
            if fixed_size.value:
                # Version from file metadata.
                major, minor, build = fixed_info[9], fixed_info[8], fixed_info[11]
                return f"{major}.{minor}.{build}"

            # Fallback: file date.
        mtime = os.path.getmtime(engine_path)
        return datetime.fromtimestamp(mtime).strftime("%d.%m.%y")
    except Exception:
        return "Active"

def get_all_engines_status() -> list:
    """
    Return a list of all engines and their status.
    This replaces the old CLI menu and feeds the GUI instead.
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
    Download and extract the selected engine.
    Return True on success and False on failure.
    The callback is used to send status text back to the GUI.
    """
    def log(msg):
        if callback: callback(msg)
        else: print(f"[ENGINE MANAGER] {msg}")

    log(f"Preparing download for {engine_name}...")
    engine_name = str(engine_name).strip().lower()
    zip_path = os.path.join(cfg.BASE_DIR, f"{engine_name}_temp.zip")
    download_url = ""
    direct_downloads = getattr(cfg, "DIRECT_DOWNLOADS", {})

    # Determine the download source.
    if engine_name in direct_downloads:
        download_url = str(direct_downloads[engine_name]).strip()
    elif engine_name in cfg.ENGINE_REPOS:
        repo = cfg.ENGINE_REPOS[engine_name]
        if not repo or repo.startswith("http://") or repo.startswith("https://"):
            log("Engine source is not a GitHub repo reference. Configure DIRECT_DOWNLOADS instead.")
            return False

        api_url = f"https://api.github.com/repos/{repo}/releases/latest"
        try:
            data = _get_release_data(repo)
            assets = data.get("assets", [])

            # Prefer a Windows x64 ZIP, otherwise any Windows ZIP.
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
                log(f"Found version: {selected.get('name', 'Unknown')}")
            elif assets:
                log("Release found, but no matching Windows ZIP asset was available.")
            else:
                log("Release found, but it does not contain any assets.")
        except Exception as e:
            log(f"GitHub API error: {e}")
            return False

    # Download, validate, and extract the ZIP archive.
    if download_url:
        try:
            log(f"Downloading: {download_url.split('/')[-1]}...")
            _download_file(download_url, zip_path, timeout=45, retries=3)

            if not zipfile.is_zipfile(zip_path):
                raise ValueError("Downloaded file is not a valid ZIP archive.")

            log("Extracting files...")
            target_dir = os.path.join(cfg.ENGINE_BASE_DIR, engine_name)
            os.makedirs(target_dir, exist_ok=True)
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(target_dir)

            if os.path.exists(zip_path):
                os.remove(zip_path)

            # Move the EXE out of nested folders if needed.
            exe_to_find = f"{engine_name}.exe"
            for root, dirs, files in os.walk(target_dir):
                if exe_to_find in files:
                    for f in os.listdir(root):
                        src = os.path.join(root, f)
                        dst = os.path.join(target_dir, f)
                        if not os.path.exists(dst):
                            os.replace(src, dst)
                    break

            log(f"{engine_name.upper()} installed successfully.")
            return True

        except Exception as e:
            log(f"Download/extract error: {e}")
            if os.path.exists(zip_path):
                try: os.remove(zip_path)
                except: pass
            return False
    else:
        log("No suitable Windows ZIP was found. Possible causes: no binary release, API rate limit, or temporary server issue.")
        return False