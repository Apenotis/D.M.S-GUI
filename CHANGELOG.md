# Changelog

## [3.2.4] - 2026-04-15

### Added
- Added duplicate detection during Install folder imports for both IWAD and PWAD entries with user choice (Skip / Overwrite / Cancel All).
- Added release-gate tests for 4-column DOOM map distribution to catch empty-column regressions before release.

### Fixed
- Fixed 4-column DOOM map list distribution so all columns are used as evenly as possible.
- Fixed bundled icon loading in frozen builds by resolving assets from the PyInstaller runtime path.
- Extended official IWAD recognition and DB insertion for additional original files (including TNT/Plutonia extras and Hexen variants) during import/setup.

### Changed
- Release pipeline now runs pytest as part of validation before packaging.

## [3.2.3] - 2026-04-15

### Added
- Smart Import Scan for local install packages with optional startup scan toggle.
- Backup and restore actions in the GUI, including automatic guard backups before update and delete actions.
- Backup retention pruning support and expanded backup payload coverage for recovery scenarios.

### Fixed
- Removed obsolete global `use_mods` config flow; mod handling now follows GUI selection by default with per-map `NoMods` override.
- Build and distribution now consistently include custom app icons (`assets/dms_icon.ico` and `assets/dms_icon.png`).
- `build_exe.bat` now prefers the local project virtual environment instead of a hardcoded path.

### Changed
- Release automation script hardened with stricter changelog validation and safer optional flags for push/release steps.
- README updated with release script guidance, execution policy workaround, and a quick release checklist.

## [3.2.2] - 2026-04-13

### Added
- ZIP-based launcher updates now restore the tested project package instead of only replacing a single file.
- Added a standalone recovery launcher and startup chain via `start.bat`.
- Automatic rollback prompt now appears after detected startup failures when backups are available.

### Fixed
- Package updates now include `start.bat` and `recovery_launcher.py` so the recovery path is updated together with the launcher.
- Rollback flow was live-tested with an intentionally broken launcher start and validated against the generated backup ZIP.

## [3.2.1] - 2026-04-13

### Fixed
- Updater now reads launcher version from a dedicated version source (`UPDATE.launcher_version_file`) to avoid mixed file responsibilities.
- Updater now writes to the configured launcher target file path instead of always using the running script path.
- Added safety guards so updates can only write Python files inside the launcher base directory.
- Added payload validation for `Gui.py` updates (rejects invalid code that does not look like launcher GUI code).
- Rollback and backup lookup now use the configured launcher target consistently.

## [3.2] - 2026-04-13

### Added
- Setup Wizard now shows live install status while engines are being downloaded and installed.
- API map installs now show a progress popup so users get immediate feedback after clicking install.

### Fixed
- Setup Wizard IWAD detection now uses case-insensitive filename checks (fixes false missing states like hexen.wad).
- IWAD imports now auto-create missing base IWAD launcher entries (Doom, Doom II, Heretic, Hexen, Plutonia, TNT) when available.
- PyInstaller packaging now includes all dms_core modules reliably for the EXE build.

## [3.1] - 2026-04-12

### Added
- Live search bar above the map table
- Sort dropdown (Insertion Order / Newest First / Name A-Z / Favorites First / Last Played)
- Quick filter chips (Alle / Doom / Heretic / Hexen)
- NEW badge for recently installed maps (72h window)
- Map Preview panel with game-type tag
- 'Bild setzen' button to assign preview images per map
- Install toast notification (bottom-right, auto-hide 9s) with 'Anspringen' button
- In-app Changelog dialog (📝 What's New button)
- Exit button below the Start button
- Extended stats dashboard (Cleared %, Favorites, NEW count, View status)

### Fixed
- Random map button crash
- Database sorting now preserves insertion order

### Changed
- Removed FAVORIT/NOMODS quick filter chips
- Improved map list responsiveness

## [3.0] - 2026-04-01

### Initial Release
- Core Doom map management system
- Engine manager for GZDoom, UZDoom, DSDA-Doom, etc.
- Doomworld idgames API integration
- Map installation and registry
- Mod management system
- Database viewer with export (CSV, JSON)
