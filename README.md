# D.M.S GUI - Doom Management System

D.M.S GUI is a desktop launcher for Classic Doom.
It helps you manage engines, install maps, organize your library, and start games with optional mods.

## What It Does

- Launches Classic Doom maps with your selected source port
- Installs maps from Doomworld (idgames API)
- Installs custom maps from local files/folders
- Manages map metadata in a local SQLite database
- Supports map status flags: Clear, Favorite, NoMods
- Tracks total playtime and last played info
- Live search, quick filter chips, sort modes
- NEW badge for recently installed maps (72h window)
- Install toast notification with jump-to-map button
- Map preview panel with game-type tag
- In-app changelog / What's New dialog

## Core Features

### Engine Management
- Supported engines: gzdoom, uzdoom, dsda-doom, woof, nugget-doom, odamex, zandronum, lzdoom
- Install/update engines directly from the GUI

### Map Installation
- Browse and install from Doomworld idgames API
- Import local files/folders
- Maps are auto-registered in the local SQLite database

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
Download the latest release zip, extract it, and run `DMS-GUI.exe` inside the folder.

### Windows — From Source
```
start.bat
```

### Python (any platform)
```
python Gui.py
```

## Release Contents

The release zip (`dms-v3.1-win64.zip`) contains a self-contained Windows build:
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
