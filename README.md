# D.M.S GUI - Doom Management System

D.M.S GUI is a desktop launcher for Classic Doom.
It helps you manage engines, install maps, organize your library, and start games with optional mods.

## What It Does

- Launches Classic Doom maps with your selected source port
- Installs maps from Doomworld (idgames API)
- Installs custom maps from local files/folders
- Manages map metadata in a local SQLite database
- Supports map status flags like clear, favorite, and no-mod mode
- Tracks total playtime and last played information

## Core Features

### 1. Engine Management
- Supported engines include:
  - gzdoom
  - uzdoom
  - dsda-doom
  - woof
  - nugget-doom
  - odamex
  - zandronum
  - lzdoom
- Engine install/update from configured release sources
- Active engine selection in GUI

### 2. Map Installation

#### Doomworld API Import
- Browse and search idgames content
- Install directly from the API browser
- Auto-register installed maps in the local database

#### Manual/Custom Import
- Import from local files via Install flow
- Manual map entry form in GUI for custom records
- Supports multiple categories (IWAD/PWAD/EXTRA)

### 3. Library Management
- Clear tag per map (Cleared)
- Favorite tag per map (Favorite)
- NoMods flag per map (NoMods)
- Per-map custom launch arguments (ARGS)
- Context menu actions for quick updates

### 4. Mod Management
- Mod checkbox panel in GUI
- Category folders:
  - mods/doom
  - mods/heretic
  - mods/hexen
  - mods/Wolfenstein
- Recursive mod file discovery during launch

### 5. Tracking and Stats
- Total playtime tracking
- Last played timestamp
- Session/game result integration
- Optional debugger/tracker toggle in GUI

### 6. Database and Tools
- Uses SQLite (`maps.db`) as local data storage
- DB Viewer dialog with:
  - filtering (category/IWAD/search)
  - CSV export
  - JSON export

## Project Structure

- `Gui.py` - Main GUI application
- `dms_core/` - Core modules (config, db, installer, runner, updater, api, etc.)
- `config.ini` - Runtime settings
- `maps.db` - SQLite database
- `start.bat` - Quick launcher

## First Start

You can start with a minimal package (`Gui.py`, `start.bat`, `dms_core/`).
On first run, the app/bootstrap setup creates required folders and config/database scaffolding.

## Run

### Windows (recommended)
- Run `start.bat`

### Python
- Run `python Gui.py`

## Snapshot Tool (Testing)

The project includes a snapshot helper for quick test copies:

- `make_test_snapshot.bat`
- `make_test_snapshot.py`

Default mode is `minimal`.

## Notes

- This launcher targets Classic Doom workflows.
- Keep your IWAD files in the `iwad/` folder.
- Engine binaries are expected under `Engines/<engine>/`.
