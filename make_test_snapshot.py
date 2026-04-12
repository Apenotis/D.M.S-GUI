import argparse
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SNAPSHOT_BASE = ROOT / "_test_snapshots"


def _copy_if_exists(src: Path, dst: Path):
    if not src.exists():
        return
    if src.is_dir():
        shutil.copytree(src, dst)
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def _create_full_snapshot(target: Path):
    required = [
        "Gui.py",
        "start.bat",
        "dms_core",
        "config.ini",
        "maps.db",
        "Engines",
        "Install",
        "iwad",
        "mods",
        "pwad",
    ]
    for item in required:
        _copy_if_exists(ROOT / item, target / item)


def _create_clean_snapshot(target: Path):
    required = ["Gui.py", "start.bat", "dms_core"]
    for item in required:
        _copy_if_exists(ROOT / item, target / item)

    # Empty scaffold created by first-run setup/use
    for folder in [
        "Engines",
        "Install",
        "iwad",
        "pwad",
        "mods",
        "mods/doom",
        "mods/heretic",
        "mods/hexen",
        "mods/Wolfenstein",
    ]:
        (target / folder).mkdir(parents=True, exist_ok=True)


def _create_minimal_snapshot(target: Path):
    required = ["Gui.py", "start.bat", "dms_core"]
    for item in required:
        _copy_if_exists(ROOT / item, target / item)


def create_snapshot(mode: str, base_dir: Path) -> Path:
    base_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    target = base_dir / f"dms_{mode}_{stamp}"

    if mode == "full":
        _create_full_snapshot(target)
    elif mode == "clean":
        _create_clean_snapshot(target)
    elif mode == "minimal":
        _create_minimal_snapshot(target)
    else:
        raise ValueError(f"Unsupported mode: {mode}")

    return target


def main():
    parser = argparse.ArgumentParser(description="Create test snapshots of the DMS project.")
    parser.add_argument(
        "--mode",
        choices=["full", "clean", "minimal"],
        default="minimal",
        help="Snapshot type: full (with data), clean (empty scaffold), minimal (code only).",
    )
    parser.add_argument(
        "--out",
        default=str(SNAPSHOT_BASE),
        help="Output base directory for snapshots (default: _test_snapshots).",
    )
    args = parser.parse_args()

    out_base = Path(args.out)
    target = create_snapshot(args.mode, out_base)

    print(f"Snapshot created: {target}")
    print(f"Mode: {args.mode}")
    print("Ready to test.")


if __name__ == "__main__":
    main()
