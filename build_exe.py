from pathlib import Path
import os
import subprocess
import sys

import dms_core.config as cfg


def main() -> int:
    root = Path(__file__).resolve().parent
    version = str(cfg.APP_VERSION).strip() or "dev"

    dist_subdir = f"dms-v{version}"
    dist_path = root / "dist" / dist_subdir
    build_path = root / "build" / dist_subdir
    icon_path = root / "assets" / "dms_icon.ico"
    assets_path = root / "assets"

    dms_hidden = [
        "dms_core.config",
        "dms_core.database",
        "dms_core.api",
        "dms_core.engine_manager",
        "dms_core.game_runner",
        "dms_core.initialization",
        "dms_core.installer",
        "dms_core.map_loader",
        "dms_core.setup_wizard",
        "dms_core.updater",
        "dms_core.utils",
    ]
    hidden_args = []
    for mod in dms_hidden:
        hidden_args += ["--hidden-import", mod]

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--onedir",
        "--name",
        "DMS-GUI",
        "--icon",
        str(icon_path),
        "--distpath",
        str(dist_path),
        "--workpath",
        str(build_path),
        *hidden_args,
        "Gui.py",
    ]

    if assets_path.exists():
        cmd.extend([
            "--add-data",
            f"{assets_path}{os.pathsep}assets",
        ])

    print("Building DMS GUI executable...")
    print(f"Version: {version}")
    print(f"Dist path: {dist_path}")

    result = subprocess.run(cmd, cwd=root)
    if result.returncode != 0:
        return result.returncode

    print("\nBuild done.")
    print(f"Output folder: {dist_path / 'DMS-GUI'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
