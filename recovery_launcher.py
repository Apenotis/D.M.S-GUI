import ctypes
import json
import os
import subprocess
import sys
import zipfile


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GUI_FILE = os.path.join(BASE_DIR, "Gui.py")
BACKUP_DIR = os.path.join(BASE_DIR, "update_backups")
FAIL_MARKER = os.path.join(BASE_DIR, "update_start_fail.json")

MB_OK = 0x00000000
MB_ICONINFORMATION = 0x00000040
MB_ICONWARNING = 0x00000030
MB_ICONERROR = 0x00000010
MB_YESNO = 0x00000004
MB_DEFBUTTON1 = 0x00000000
IDYES = 6


def _message_box(text: str, title: str, flags: int) -> int:
    return ctypes.windll.user32.MessageBoxW(None, str(text), str(title), int(flags))


def info(title: str, text: str) -> None:
    _message_box(text, title, MB_OK | MB_ICONINFORMATION)


def warn(title: str, text: str) -> None:
    _message_box(text, title, MB_OK | MB_ICONWARNING)


def error(title: str, text: str) -> None:
    _message_box(text, title, MB_OK | MB_ICONERROR)


def ask_yes_no(title: str, text: str) -> bool:
    result = _message_box(text, title, MB_YESNO | MB_ICONWARNING | MB_DEFBUTTON1)
    return result == IDYES


def get_backups() -> list[str]:
    if not os.path.isdir(BACKUP_DIR):
        return []
    backups = []
    for name in os.listdir(BACKUP_DIR):
        if name.lower().startswith("backup_") and name.lower().endswith(".zip"):
            backups.append(os.path.join(BACKUP_DIR, name))
    backups.sort(reverse=True)
    return backups


def load_fail_marker() -> dict:
    if not os.path.exists(FAIL_MARKER):
        return {}
    try:
        with open(FAIL_MARKER, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def clear_fail_marker() -> None:
    try:
        if os.path.exists(FAIL_MARKER):
            os.remove(FAIL_MARKER)
    except Exception:
        pass


def restore_backup(backup_zip: str) -> bool:
    try:
        if not os.path.exists(backup_zip):
            return False
        with zipfile.ZipFile(backup_zip, "r") as zf:
            zf.extractall(BASE_DIR)
        clear_fail_marker()
        return True
    except Exception as exc:
        error("Rollback", f"Backup konnte nicht wiederhergestellt werden.\n\n{exc}")
        return False


def offer_rollback(reason_text: str) -> bool:
    backups = get_backups()
    if not backups:
        return False

    latest = os.path.basename(backups[0])
    prompt = (
        "Der Launcher konnte nicht sauber gestartet werden.\n\n"
        f"Grund:\n{reason_text}\n\n"
        f"Neuestes Backup:\n{latest}\n\n"
        "Soll dieses Backup jetzt wiederhergestellt werden?"
    )
    if not ask_yes_no("Rollback anbieten", prompt):
        return False

    if restore_backup(backups[0]):
        info("Rollback", "Backup wurde erfolgreich wiederhergestellt. Der Launcher wird jetzt erneut gestartet.")
        return True
    return False


def run_gui() -> int:
    if not os.path.exists(GUI_FILE):
        error("Startfehler", f"Gui.py wurde nicht gefunden:\n{GUI_FILE}")
        return 1

    env = os.environ.copy()
    env["PYTHONPATH"] = BASE_DIR
    proc = subprocess.run([sys.executable, GUI_FILE], cwd=BASE_DIR, env=env)
    return int(proc.returncode)


def main() -> int:
    previous_fail = load_fail_marker()
    if previous_fail:
        details = str(previous_fail.get("details", "Vorheriger Startfehler erkannt.")).strip()
        if offer_rollback(details[:1000]):
            previous_fail = {}

    attempts = 0
    while attempts < 2:
        exit_code = run_gui()
        if exit_code == 0:
            clear_fail_marker()
            return 0

        fail_info = load_fail_marker()
        detail_text = str(fail_info.get("details", "") or "").strip()
        if not detail_text:
            detail_text = f"Launcher wurde mit Exit-Code {exit_code} beendet."

        if not offer_rollback(detail_text[:1000]):
            return exit_code

        attempts += 1

    warn("Rollback", "Der Launcher wurde nach Wiederherstellung erneut beendet. Bitte Installation manuell prüfen.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())