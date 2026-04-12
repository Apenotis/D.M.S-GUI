# Doom Management System (D.M.S.) - AI Coding Assistant Instructions

## Project Overview
This is a Python-based GUI application for managing and launching Doom games using various source ports (engines) and mods. It provides a comprehensive interface for browsing, downloading, and playing Doom maps from Doomworld's idgames archive, with support for multiple engines like GZDoom, UZDoom, DSDA-Doom, etc.

## Architecture
The application follows a modular architecture with clear separation of concerns:

### Core Components (`dms_core/`)
- **`config.py`**: Central configuration management using `configparser`. Handles paths, engine lists, and settings persistence.
- **`database.py`**: CSV-based data storage system for map metadata. Uses semicolon-delimited UTF-8-sig encoded files.
- **`api.py`**: Doomworld idgames API integration for browsing and downloading maps.
- **`engine_manager.py`**: Automated engine installation from GitHub releases.
- **`game_runner.py`**: Command-line construction and game launching logic.
- **`installer.py`**: Custom map installation from local files.
- **`map_loader.py`**: Directory scanning and map discovery.
- **`updater.py`**: Application update checking.
- **`initialization.py`**: Application startup and initialization.
- **`utils.py`**: Shared utilities, including the `@tracker` decorator for logging.

### GUI Layer (`Gui.py`)
Main PySide6-based interface with:
- Engine management dialog
- Doomworld API browser
- Main map selection table with 3D-styled buttons
- Mod selection panel
- Statistics dashboard

### Data Flow
1. **Map Data**: Stored in `maps.csv` with 13 columns: `Cleared;NoMods;ID;Name;IWAD;Path;MOD;ARGS;Kategorie;Playtime;LastPlayed;RemoteID;Favorite`
2. **Configuration**: `config.ini` with sections for SETTINGS, STATS, ENGINES, UPDATE
3. **Assets**: IWADs in `iwad/`, PWADs in `pwad/`, mods in `mods/{game}/`, engines in `Engines/{engine}/`

## Key Workflows

### Game Launch Process
```python
# From Gui.py run_selected_map()
engine_path = cfg.get_engine_path()  # Builds Engines/{engine}/{engine}.exe
selected_mods = self.get_checked_mods()  # From GUI checkboxes
cmd_info = runner.get_start_command(engine_path, map_data, selected_mods)
success = runner.run_game(engine_path, map_data, selected_mods)
```

### Engine Installation
```python
# From engine_manager.py
engines.install_engine(engine_name, callback=update_ui)
# Downloads latest release from GitHub, extracts to Engines/{engine}/
```

### Map Download
```python
# From api.py
results = api.get_top_wads(category)  # doom_megawads, doom2_megawads, heretic, hexen
success, msg = api.download_idgames_gui(file_data, callback=progress_update)
```

## Development Conventions

### File Encoding & Formats
- **Config/CSV**: UTF-8-sig encoding (`encoding="utf-8-sig"`)
- **CSV Delimiter**: Semicolon (`;`) not comma
- **Config Sections**: UPPERCASE (`[SETTINGS]`, `[STATS]`)
- **Paths**: Use `os.path.join()` for cross-platform compatibility

### Error Handling
- Global exception handler in `Gui.py` logs to `dms_error.log`
- `@tracker` decorator logs function calls to `dms_tracker.log`
- Graceful degradation with try/except blocks

### GUI Patterns
- PySide6 with custom CSS styling for 3D button effects
- `QTableWidgetItem.setData(Qt.UserRole, value)` for storing IDs
- Signal/slot connections for async operations
- `QApplication.processEvents()` for UI responsiveness during long operations

### Mod Handling
- Mods are directories containing `.wad`, `.pk3`, `.pk7`, `.zip`, `.deh`, `.bex` files
- Recursive scanning: `os.walk()` to find all valid files in mod directories
- Mod lock: `NoMods` flag in CSV prevents mod loading for specific maps

### Engine Support
- Supported engines: `gzdoom`, `uzdoom`, `dsda-doom`, `woof`, `nugget-doom`, `odamex`, `zandronum`, `lzdoom`
- GitHub repos mapped in `ENGINE_REPOS` dict
- Engine-specific command line args (e.g., `+logfile` for ZDoom-based engines)

## Common Patterns

### Database Operations
```python
# Reading maps
maps = db.get_all_maps()  # Returns list of dicts
map_data = db.get_map_by_id("DOOM1")  # Case-insensitive ID lookup

# Updating status
db.toggle_map_clear(map_id)  # 0<->1 for Cleared column
db.toggle_mod_skip(map_id)   # 0<->1 for NoMods column
```

### Path Construction
```python
# IWAD path
iwad_path = os.path.join(cfg.IWAD_DIR, map_data['IWAD'])

# PWAD path
if map_data['Kategorie'] != 'IWAD':
    pwad_path = os.path.join(cfg.PWAD_DIR, map_data['Path'])
```

### Command Building
```python
cmd = [engine_exe, "-iwad", iwad_path]
if mods:
    cmd.extend(["-file"] + mod_files)
if args:
    cmd.extend(args.split())
subprocess.run(cmd, cwd=engine_dir)
```

## Launch & Development
- **Start**: `start.bat` sets `PYTHONPATH=.` and runs `python Gui.py`
- **Dependencies**: PySide6 for GUI, standard library for everything else
- **No virtual environment**: Runs in system Python (assumes PySide6 installed)
- **Logging**: Errors to `dms_error.log`, tracking to `dms_tracker.log`

## Key Files to Reference
- `dms_core/config.py`: All paths, constants, and configuration logic
- `dms_core/database.py`: CSV schema and data operations
- `dms_core/game_runner.py`: Command construction and launching
- `Gui.py`: Main UI logic and event handling
- `maps.csv`: Data structure example
- `config.ini`: Configuration format

## Gotchas
- CSV uses semicolons, not commas
- UTF-8-sig required for proper German character handling
- Engine EXEs expected at `Engines/{name}/{name}.exe`
- Mod directories scanned recursively for valid extensions
- `NoMods` flag overrides user mod selection
- Doomworld API has rate limits; use callbacks for progress updates