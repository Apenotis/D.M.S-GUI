# D.M.S GUI - Doom Management System

D.M.S GUI is a desktop launcher for Classic Doom.
It helps you manage engines, install maps, organize your library, and start games with optional mods.

## What It Does

- Launches Classic Doom maps with your selected source port
- Installs maps from Doomworld (idgames API)
- Installs custom maps from local files/folders
- Smart Import Scan for queued local installs in Install/
- Manages map metadata in a local SQLite database
- Supports map status flags: Clear, Favorite, NoMods
- Tracks total playtime and last played info
- Live search, quick filter chips, sort modes
- NEW badge for recently installed maps (72h window)
- Install toast notification with jump-to-map button
- Map preview panel with game-type tag
- Manual backup/restore plus automatic safety backups before risky actions
- In-app changelog / What's New dialog

## Core Features

### Engine Management
- Supported engines: gzdoom, uzdoom, dsda-doom, woof, nugget-doom, odamex, zandronum, lzdoom
- Install/update engines directly from the GUI

### Map Installation
- Browse and install from Doomworld idgames API
- Import local files/folders
- Run Smart Import Scan to detect and install content dropped into `Install/`
- Maps are auto-registered in the local SQLite database

### Safety Tools
- Create manual backups from the GUI
- Restore previous backups when an update or delete needs to be rolled back
- Optional startup import scan and automatic backup retention

### Library Management
- Clear / Favorite / NoMods flags per map
- Per-map custom launch arguments
- Context menu for quick actions
- Sort by: Insertion Order, Newest First, Name A-Z, Favorites First, Last Played

### Mod Management
- Mod checkbox panel (doom / heretic / hexen / Wolfenstein categories)
- Recursive mod file discovery at launch

### Stats Dashboard
- Cleared %, Favorites count, NEW count, current view label
- Total playtime and last played timestamps

## Project Structure

```
start.bat       # Quick launcher (Windows)
Gui.py          # Main GUI application
dms_core/       # Core modules: config, database, api, game_runner, installer, engine_manager, updater, ...
```

On first run the app creates all required folders (`iwad/`, `pwad/`, `mods/`, `Engines/`) and scaffolds `config.ini` and `maps.db` automatically.

## Run

### Windows — Compiled Release (recommended)
Download the latest release zip (`dms-vX.Y.Z-win64.zip`), extract it, and run `DMS-GUI.exe` inside the folder.

### Windows — From Source
```
start.bat
```

### Python (any platform)
```
python Gui.py
```

### Release Script (PowerShell)
If your system blocks local scripts, use a one-time execution policy bypass:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\release.ps1 -NewVersion X.Y.Z
```

Safe test run without pushing or creating a GitHub release:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\release.ps1 -NewVersion X.Y.Z-test -SkipPush -SkipGitHubRelease
```

### Quick Release Checklist
1. Ensure the working tree is clean (`git status`).
2. Prepare final notes in `CHANGELOG.md` (no placeholders).
3. Run a safe test flow first:
  `powershell -NoProfile -ExecutionPolicy Bypass -File .\release.ps1 -NewVersion X.Y.Z-test -SkipPush -SkipGitHubRelease`
4. Run the real release:
  `powershell -NoProfile -ExecutionPolicy Bypass -File .\release.ps1 -NewVersion X.Y.Z`
5. Verify the built app in `dist/dms-vX.Y.Z/DMS-GUI`.
6. Confirm ZIP artifact `dms-vX.Y.Z-win64.zip` is present and opens correctly.

## Release Contents

The release zip (`dms-vX.Y.Z-win64.zip`) contains a self-contained Windows build:
```
DMS-GUI/
  DMS-GUI.exe       # Main executable
  _internal/        # PySide6 runtime and dependencies
```
No Python installation required.

## Notes

- This launcher targets Classic Doom workflows.
- Keep your IWAD files in the `iwad/` folder.
- Engine binaries are expected under `Engines/<engine>/`.
- Smart Import Scan checks the `Install/` folder on demand, or optionally once at startup.
