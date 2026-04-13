# Changelog

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
