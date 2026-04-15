import glob
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from datetime import datetime

import dms_core.config as cfg


UPDATE_BACKUP_DIR = os.path.join(cfg.BASE_DIR, "update_backups")
START_FAIL_FILE = os.path.join(cfg.BASE_DIR, "update_start_fail.json")
PACKAGE_UPDATE_PATHS = ["Gui.py", "dms_core", "CHANGELOG.md", "start.bat", "recovery_launcher.py"]

# ============================================================================
# Launcher and engine updates
# ============================================================================

def check_uzdoom_update() -> tuple[bool, str]:
    """
    Check the GitHub API for a newer UZDoom release.
    Returns a tuple of (is_newer_than_4_14_3, latest_version_string).
    """
    try:
        req = urllib.request.Request("https://api.github.com/repos/UZDoom/UZDoom/releases/latest")
        req.add_header("User-Agent", "Python-Launcher")
        with urllib.request.urlopen(req, timeout=2) as response:
            data = json.loads(response.read().decode())
            latest = data.get("tag_name", "")
            return latest != "4.14.3", latest
    except Exception as e:
        print(f"[UPDATER] Error while checking for a UZDoom update: {e}")
        return False, "4.14.3"

def is_newer(remote: str, local: str) -> bool:
    """Vergleicht Versions-Strings wie '3.1' oder '3.0.5' mathematisch."""
    try:
        # Split '3.1.0' into [3, 1, 0] for proper list comparison.
        remote_parts = [int(x) for x in str(remote).split(".")]
        local_parts = [int(x) for x in str(local).split(".")]
        return remote_parts > local_parts
    except Exception:
        return False


def _fetch_text(url: str, timeout: int = 5) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8-sig")


def _fetch_json(url: str, timeout: int = 8) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8-sig"))


def _download_file(url: str, dest_path: str, timeout: int = 20) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as response, open(dest_path, "wb") as f:
        f.write(response.read())


def _normalize_version(version: str) -> str:
    return str(version or "").strip().lstrip("vV")


def _ensure_backup_dir() -> None:
    os.makedirs(UPDATE_BACKUP_DIR, exist_ok=True)


def _find_project_root(root_dir: str) -> str:
    for cur_root, dirs, files in os.walk(root_dir):
        if "Gui.py" in files and "dms_core" in dirs:
            return cur_root
    return ""


def _copy_tree(src: str, dst: str) -> None:
    if not os.path.exists(src):
        return
    if os.path.isdir(src):
        os.makedirs(dst, exist_ok=True)
        for entry in os.listdir(src):
            _copy_tree(os.path.join(src, entry), os.path.join(dst, entry))
    else:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)


def create_update_backup(label: str) -> str:
    _ensure_backup_dir()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_label = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(label or "manual"))
    backup_path = os.path.join(UPDATE_BACKUP_DIR, f"backup_{safe_label}_{stamp}.zip")

    with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in PACKAGE_UPDATE_PATHS + ["config.ini", "maps.db", "maps.csv"]:
            abs_path = os.path.join(cfg.BASE_DIR, rel)
            if not os.path.exists(abs_path):
                continue
            if os.path.isdir(abs_path):
                for cur_root, _, files in os.walk(abs_path):
                    for file_name in files:
                        src = os.path.join(cur_root, file_name)
                        arc = os.path.relpath(src, cfg.BASE_DIR)
                        zf.write(src, arc)
            else:
                zf.write(abs_path, rel)

    return backup_path


def prune_update_backups(keep_count: int = 10) -> int:
    """Delete older ZIP backups and keep only the newest entries."""
    try:
        keep = max(1, int(keep_count))
    except Exception:
        keep = 10

    files = get_update_backups()
    removed = 0
    for stale_path in files[keep:]:
        try:
            os.remove(stale_path)
            removed += 1
        except Exception:
            continue
    return removed


def get_update_backups() -> list:
    _ensure_backup_dir()
    files = sorted(glob.glob(os.path.join(UPDATE_BACKUP_DIR, "backup_*.zip")), reverse=True)
    return files


def restore_update_backup(backup_zip_path: str) -> bool:
    try:
        if not os.path.exists(backup_zip_path):
            return False
        with zipfile.ZipFile(backup_zip_path, "r") as zf:
            zf.extractall(cfg.BASE_DIR)
        return True
    except Exception as e:
        print(f"[UPDATER] Error while restoring the ZIP backup: {e}")
        return False


def restore_latest_update_backup() -> bool:
    backups = get_update_backups()
    if not backups:
        return False
    return restore_update_backup(backups[0])


def mark_start_failure(details: str) -> None:
    try:
        data = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "details": str(details or "")[:30000],
            "latest_backup": get_update_backups()[0] if get_update_backups() else "",
        }
        with open(START_FAIL_FILE, "w", encoding="utf-8-sig") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def clear_start_failure_marker() -> None:
    try:
        if os.path.exists(START_FAIL_FILE):
            os.remove(START_FAIL_FILE)
    except Exception:
        pass


def get_start_failure_info() -> dict:
    try:
        if not os.path.exists(START_FAIL_FILE):
            return {}
        with open(START_FAIL_FILE, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _get_launcher_target_path() -> str:
    target_rel = cfg.config.get("UPDATE", "launcher_file", fallback="Gui.py").strip() or "Gui.py"
    target_path = os.path.abspath(os.path.join(cfg.BASE_DIR, target_rel))
    base_dir = os.path.abspath(cfg.BASE_DIR)

    # Security guard: updates may only write Python files inside BASE_DIR.
    if not target_path.startswith(base_dir + os.sep):
        raise ValueError(f"Unsafe update path outside BASE_DIR: {target_path}")
    if not target_path.lower().endswith(".py"):
        raise ValueError(f"Update target is not a Python file: {target_path}")

    return target_path


def _get_launcher_version_path() -> str:
    version_rel = cfg.config.get("UPDATE", "launcher_version_file", fallback="dms_core/config.py").strip() or "dms_core/config.py"
    version_path = os.path.abspath(os.path.join(cfg.BASE_DIR, version_rel))
    base_dir = os.path.abspath(cfg.BASE_DIR)

    if not version_path.startswith(base_dir + os.sep):
        raise ValueError(f"Unsafe version path outside BASE_DIR: {version_path}")
    if not version_path.lower().endswith(".py"):
        raise ValueError(f"Version target is not a Python file: {version_path}")

    return version_path


def _sync_local_version(remote_version: str) -> None:
    """Update APP_VERSION in the local version file after a successful update."""
    version_path = _get_launcher_version_path()
    if not os.path.exists(version_path):
        return

    with open(version_path, "r", encoding="utf-8-sig") as f:
        current = f.read()

    updated = re.sub(
        r'APP_VERSION\s*=\s*"[^"]+"',
        f'APP_VERSION = "{remote_version}"',
        current,
        count=1,
    )

    if updated != current:
        with open(version_path, "w", encoding="utf-8-sig") as f:
            f.write(updated)

def check_launcher_update() -> dict:
    """
    Check whether a newer launcher version is available.
    Returns a dictionary the GUI can process directly.
    """
    result = {
        "update_available": False,
        "remote_version": "",
        "remote_code": "",
        "update_mode": "script",
        "package_url": "",
        "changelog_text": "",
        "changelog_url": "",
        "error": None,
    }
    
    try:
        repo = cfg.config.get("UPDATE", "launcher_repo", fallback="").strip()
        if repo:
            release_api = f"https://api.github.com/repos/{repo}/releases/latest"
            release = _fetch_json(release_api, timeout=8)
            tag_name = str(release.get("tag_name", "") or "")
            remote_version = _normalize_version(tag_name)
            if remote_version:
                result["remote_version"] = remote_version
                result["changelog_text"] = str(release.get("body", "") or "")
                result["changelog_url"] = f"https://github.com/{repo}/releases/tag/{tag_name}"
                result["package_url"] = str(release.get("zipball_url", "") or "")
                result["update_mode"] = "package"

                if not result["changelog_text"]:
                    branch = cfg.config.get("UPDATE", "launcher_branch", fallback="main").strip() or "main"
                    md_url = f"https://raw.githubusercontent.com/{repo}/{branch}/CHANGELOG.md"
                    result["changelog_url"] = md_url
                    try:
                        result["changelog_text"] = _fetch_text(md_url, timeout=5)
                    except Exception:
                        result["changelog_text"] = ""

                if is_newer(remote_version, cfg.APP_VERSION):
                    result["update_available"] = True
                return result

        update_url = cfg.get_launcher_update_url()
        version_url = cfg.get_launcher_version_url()
        if not update_url:
            result["error"] = "Launcher update source is not configured (UPDATE.launcher_update_url or launcher_repo)."
            return result
        if not version_url:
            result["error"] = "Launcher version source is not configured."
            return result

        version_code = _fetch_text(version_url, timeout=5)
        remote_code = _fetch_text(update_url, timeout=5)

        repo = cfg.config.get("UPDATE", "launcher_repo", fallback="").strip()
        branch = cfg.config.get("UPDATE", "launcher_branch", fallback="main").strip() or "main"
        if repo:
            changelog_url = f"https://raw.githubusercontent.com/{repo}/{branch}/CHANGELOG.md"
            result["changelog_url"] = changelog_url
            try:
                result["changelog_text"] = _fetch_text(changelog_url, timeout=5)
            except Exception:
                result["changelog_text"] = ""

        match = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', version_code)
        if match:
            remote_version = match.group(1)
            result["remote_version"] = remote_version
            result["remote_code"] = remote_code

            if is_newer(remote_version, cfg.APP_VERSION):
                result["update_available"] = True
                
    except Exception as e:
        result["error"] = str(e)
        print(f"[UPDATER] Error while checking for updates: {e}")

    return result

def apply_launcher_update(remote_version: str, remote_code: str) -> bool:
    """
    Apply a script-based launcher update, create backups, and write the new code.
    This must be called by the main app or GUI, which then initiates a restart.
    """
    try:
        target_path = _get_launcher_target_path()

        # Plausibility check for GUI updates: prevent unrelated files from replacing Gui.py.
        if os.path.basename(target_path).lower() == "gui.py":
            if "class DoomManagerGUI" not in remote_code:
                raise ValueError("Remote code does not look like Gui.py (DoomManagerGUI is missing).")

        # 1. Script backup
        backup_path = f"{target_path}.bak_v{cfg.APP_VERSION}"
        shutil.copy2(target_path, backup_path)

        # 2. Database backup
        if os.path.exists(cfg.DB_FILE):
            db_backup_path = f"{cfg.DB_FILE}.bak_v{cfg.APP_VERSION}"
            shutil.copy2(cfg.DB_FILE, db_backup_path)

        # Write the update
        remote_code_fixed = remote_code.replace("\r\n", "\n")
        with open(target_path, "w", encoding="utf-8-sig") as f:
            f.write(remote_code_fixed)

        # Also update the local version file so the next start does not show the dialog again.
        _sync_local_version(remote_version)

        return True
    except Exception as e:
        print(f"[UPDATER] Error while applying the update: {e}")
        return False


def apply_launcher_package_update(update_info: dict) -> bool:
    """Apply a ZIP package update based on a complete tested release."""
    try:
        remote_version = str(update_info.get("remote_version", "") or "").strip()
        package_url = str(update_info.get("package_url", "") or "").strip()
        if not remote_version or not package_url:
            raise ValueError("Package update information is incomplete (missing version or URL).")

        create_update_backup(f"preupdate_v{cfg.APP_VERSION}")

        with tempfile.TemporaryDirectory(prefix="dms_update_") as tmp:
            zip_path = os.path.join(tmp, "release.zip")
            extract_dir = os.path.join(tmp, "extract")

            _download_file(package_url, zip_path, timeout=40)
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)

            project_root = _find_project_root(extract_dir)
            if not project_root:
                raise ValueError("Project root not found inside ZIP (Gui.py/dms_core missing).")

            for rel in PACKAGE_UPDATE_PATHS:
                src = os.path.join(project_root, rel)
                dst = os.path.join(cfg.BASE_DIR, rel)
                if os.path.exists(dst) and os.path.isfile(dst):
                    os.remove(dst)
                _copy_tree(src, dst)

        _sync_local_version(remote_version)
        return True
    except Exception as e:
        print(f"[UPDATER] Error while applying the package update: {e}")
        return False

def get_available_backups() -> list:
    """
    Search for available backups (.bak_v*) and return them as a list.
    """
    target_path = _get_launcher_target_path()
    backup_files = sorted(glob.glob(f"{target_path}.bak_v*"), reverse=True)
    return backup_files

def apply_rollback(backup_file_path: str) -> bool:
    """
    Restore an older script version together with its matching database backup.
    """
    try:
        target_path = _get_launcher_target_path()
        version_suffix = backup_file_path.split(".bak_")[-1]
        selected_db_bak = f"{cfg.DB_FILE}.bak_{version_suffix}"

        # Save the current state as a "broken" snapshot.
        shutil.copy2(target_path, f"{target_path}.broken")
        if os.path.exists(cfg.DB_FILE):
            shutil.copy2(cfg.DB_FILE, f"{cfg.DB_FILE}.broken")

        # Restore script
        shutil.copy2(backup_file_path, target_path)

        # Restore database if a backup exists
        if os.path.exists(selected_db_bak):
            shutil.copy2(selected_db_bak, cfg.DB_FILE)

        return True
    except Exception as e:
        print(f"[UPDATER] Rollback error: {e}")
        return False