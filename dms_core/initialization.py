import configparser
import os
from datetime import datetime

import dms_core.config as cfg


def run_initial_setup() -> bool:
    """Create the full base structure needed for first start and tests."""
    setup_activity = False

    # 1. Ensure the directory structure exists.
    required_dirs = [
        cfg.IWAD_DIR,
        cfg.PWAD_DIR,
        cfg.ENGINE_BASE_DIR,
        os.path.join(cfg.BASE_DIR, "mods"),
        os.path.join(cfg.BASE_DIR, "Install"),
        os.path.join(cfg.BASE_DIR, "mods", "doom"),
        os.path.join(cfg.BASE_DIR, "mods", "heretic"),
        os.path.join(cfg.BASE_DIR, "mods", "hexen"),
        os.path.join(cfg.BASE_DIR, "mods", "Wolfenstein"),
    ]

    for path in required_dirs:
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)
            setup_activity = True

    # 2. Create or extend config.ini.
    config = configparser.ConfigParser()
    if os.path.exists(cfg.CONFIG_FILE):
        config.read(cfg.CONFIG_FILE, encoding="utf-8-sig")
    else:
        setup_activity = True

    if not config.has_section("SETTINGS"):
        config.add_section("SETTINGS")
        setup_activity = True
    if not config.has_section("STATS"):
        config.add_section("STATS")
        setup_activity = True
    if not config.has_section("UPDATE"):
        config.add_section("UPDATE")
        setup_activity = True

    defaults = {
        "SETTINGS": {
            "current_engine": "",
            "setup_completed": config.get("SETTINGS", "setup_completed", fallback="0"),
            "tracker_enabled": config.get("SETTINGS", "tracker_enabled", fallback="False"),
            "install_scan_on_startup": config.get("SETTINGS", "install_scan_on_startup", fallback="False"),
            "backup_keep_count": config.get("SETTINGS", "backup_keep_count", fallback="10"),
        },
        "STATS": {
            "totaltime": config.get("STATS", "totaltime", fallback="0"),
        },
        "UPDATE": {
            "last_check": config.get("UPDATE", "last_check", fallback=datetime.now().strftime("%Y-%m-%d")),
            "launcher_update_url": config.get("UPDATE", "launcher_update_url", fallback=""),
            "launcher_repo": config.get("UPDATE", "launcher_repo", fallback=""),
            "launcher_branch": config.get("UPDATE", "launcher_branch", fallback="main"),
            "launcher_file": config.get("UPDATE", "launcher_file", fallback="Gui.py"),
            "launcher_version_file": config.get("UPDATE", "launcher_version_file", fallback="dms_core/config.py"),
        },
    }

    for section, values in defaults.items():
        for key, value in values.items():
            if not config.has_option(section, key):
                config.set(section, key, str(value))
                setup_activity = True

    with open(cfg.CONFIG_FILE, "w", encoding="utf-8-sig") as f:
        config.write(f)

    # 3. Initialize the SQLite database safely.
    try:
        import dms_core.database as db

        if not os.path.exists(cfg.DB_FILE):
            setup_activity = True
        db.create_table_if_not_exists()
        db.migrate_from_csv()
    except Exception as e:
        print(f"[INIT] Database initialization failed: {e}")

    # 4. Reload runtime config so globals stay in sync.
    cfg.load_config()

    return setup_activity