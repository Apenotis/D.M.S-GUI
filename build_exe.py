from pathlib import Path
import subprocess
import sys

import dms_core.config as cfg


def main() -> int:
    root = Path(__file__).resolve().parent
    version = str(cfg.APP_VERSION).strip() or "dev"

    dist_subdir = f"dms-v{version}"
    dist_path = root / "dist" / dist_subdir
    build_path = root / "build" / dist_subdir

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
        "--distpath",
        str(dist_path),
        "--workpath",
        str(build_path),
        "Gui.py",
    ]

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
