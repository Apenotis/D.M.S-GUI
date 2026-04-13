"""Initial setup wizard for DMS."""

import os
import shutil
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QMessageBox, QCheckBox, QScrollArea, QWidget, QFileDialog,
    QApplication
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

import dms_core.config as cfg
import dms_core.database as db
import dms_core.engine_manager as engines
import dms_core.initialization as init

# Starter map entries that should be auto-created after importing an IWAD.
_STARTER_MAPS = {
    "doom.wad":     {"ID": "DOOM1",   "Name": "Ultimate Doom",                           "IWAD": "doom.wad"},
    "doom2.wad":    {"ID": "DOOM2",   "Name": "Doom II: Hell on Earth",                  "IWAD": "doom2.wad"},
    "heretic.wad":  {"ID": "HERETIC", "Name": "Heretic: Shadow of the Serpent Riders",   "IWAD": "heretic.wad"},
    "hexen.wad":    {"ID": "HEXEN",   "Name": "Hexen: Beyond Heretic",                   "IWAD": "hexen.wad"},
    "plutonia.wad": {"ID": "DOOM3",   "Name": "Final Doom: The Plutonia Experiment",     "IWAD": "plutonia.wad"},
    "tnt.wad":      {"ID": "DOOM4",   "Name": "Final Doom: TNT:Evilution",               "IWAD": "tnt.wad"},
}


class SetupWizard(QDialog):
    """Main first-run setup wizard."""
    
    wizard_complete = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        # Safety net: ensure the base structure exists even if the app started without pre-setup.
        init.run_initial_setup()
        self.setWindowTitle("DMS - Setup Wizard")
        self.setModal(True)
        self.resize(680, 480)
        self.step = 0
        self.folder_list = [
            "iwad",
            "pwad",
            "Engines",
            "Install",
            "mods",
            "mods/doom",
            "mods/heretic",
            "mods/hexen",
            "mods/Wolfenstein",
        ]
        
        self.layout = QVBoxLayout(self)
        self.show_welcome()
    
    def clear_layout(self):
        """Clear the current page layout."""
        while self.layout.count():
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
    
    def show_welcome(self):
        """Step 1: Welcome screen."""
        self.clear_layout()
        self.step = 1
        
        title = QLabel("Welcome to Doom Management System (D.M.S.)")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        
        folder_text = "\n".join([f"  - {folder}" for folder in self.folder_list])
        info = QLabel(
            "This wizard will help you complete the first-time setup.\n\n"
            "For a smooth first start, D.M.S. needs to create a few folders:\n"
            f"{folder_text}\n\n"
            "We will then check:\n"
            "1. Game engines (GZDoom, UZDoom, etc.)\n"
            "2. Original game files (IWAD files)\n\n"
            "Click 'Next' to continue."
        )
        info.setWordWrap(True)
        
        btn_next = QPushButton("Next ▶")
        btn_next.clicked.connect(self.check_engines)
        
        btn_skip = QPushButton("Skip")
        btn_skip.clicked.connect(self.finish_wizard)
        
        self.layout.addWidget(title)
        self.layout.addWidget(info)
        self.layout.addStretch()
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(btn_skip)
        btn_layout.addWidget(btn_next)
        self.layout.addLayout(btn_layout)
    
    def check_engines(self):
        """Step 2: Check installed engines."""
        self.clear_layout()
        self.step = 2
        
        title = QLabel("Step 1: Game Engines")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        
        installed_engines = []
        missing_engines = []
        available_engines = cfg.SUPPORTED_ENGINES
        
        for eng in available_engines:
            path = os.path.join(cfg.ENGINE_BASE_DIR, eng, f"{eng}.exe")
            if os.path.exists(path):
                installed_engines.append(eng)
            else:
                missing_engines.append(eng)
        
        info_text = ""
        if installed_engines:
            info_text += "Installed engines:\n" + \
                        "\n".join([f"  • {e.upper()}" for e in installed_engines])
        
        if missing_engines:
            if info_text:
                info_text += "\n\n"
            info_text += "Missing engines:\n" + \
                        "\n".join([f"  • {e.upper()}" for e in missing_engines]) + \
                        "\n\nYou can install them now or later."
        
        info = QLabel(info_text if info_text else "No engines found.")
        info.setWordWrap(True)
        
        btn_install_engine = QPushButton("Install Engine ⬇")
        btn_install_engine.clicked.connect(self.install_engine_dialog)
        
        btn_next = QPushButton("Next ▶")
        btn_next.clicked.connect(self.check_iwads)
        
        btn_skip = QPushButton("Skip")
        btn_skip.clicked.connect(self.finish_wizard)
        
        self.layout.addWidget(title)
        self.layout.addWidget(info)
        self.layout.addStretch()
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(btn_skip)
        btn_layout.addWidget(btn_install_engine)
        btn_layout.addWidget(btn_next)
        self.layout.addLayout(btn_layout)
    
    def install_engine_dialog(self):
        """Show a dialog for engine installation."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Select Engine")
        dialog.resize(400, 300)
        layout = QVBoxLayout(dialog)
        
        title = QLabel("Select one or more engines to install:")
        title.setFont(QFont("Arial", 12, QFont.Bold))
        layout.addWidget(title)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        
        container = QWidget()
        container_layout = QVBoxLayout(container)
        
        self.engine_checkboxes = {}
        recommended = ["uzdoom"]
        
        for eng in cfg.SUPPORTED_ENGINES:
            cb = QCheckBox(eng.upper())
            if eng in recommended:
                cb.setChecked(True)
                cb.setText(cb.text() + " (recommended)")
            self.engine_checkboxes[eng] = cb
            container_layout.addWidget(cb)
        
        container_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)
        
        status_label = QLabel("")
        status_label.setWordWrap(True)
        status_label.setStyleSheet("color: #f0c040; font-weight: bold;")
        layout.addWidget(status_label)

        btn_layout = QHBoxLayout()
        btn_install = QPushButton("Install")
        btn_cancel = QPushButton("Cancel")
        
        def do_install():
            selected = [eng for eng, cb in self.engine_checkboxes.items() if cb.isChecked()]
            if not selected:
                QMessageBox.warning(dialog, "Error", "Please select at least one engine.")
                return
            
            btn_install.setEnabled(False)
            btn_cancel.setEnabled(False)
            successful = []
            failed = []
            
            for eng in selected:
                status_label.setText(f"⬇  Downloading and installing {eng.upper()} ...")
                QApplication.processEvents()
                success = engines.install_engine(eng)
                if success:
                    successful.append(eng)
                    status_label.setText(f"✓  {eng.upper()} installed.")
                else:
                    failed.append(eng)
                    status_label.setText(f"✗  {eng.upper()} failed.")
                QApplication.processEvents()
            
            successful_txt = ", ".join([e.upper() for e in successful]) if successful else "None"
            failed_txt = ", ".join([e.upper() for e in failed]) if failed else "None"

            if successful:
                # Set the first successful engine as the default immediately.
                cfg.update_config_value("SETTINGS", "current_engine", successful[0])
                cfg.load_config()
            
            btn_install.setEnabled(True)
            btn_cancel.setEnabled(True)
            status_label.setText("")

            if successful:
                QMessageBox.information(
                    dialog,
                    "Done",
                    f"Engine installation completed.\n\nInstalled: {successful_txt}\n\nFailed: {failed_txt}\n\nActive engine: {successful[0].upper()}",
                )
            else:
                QMessageBox.warning(dialog, "Error", "All installations failed.")
            
            dialog.accept()
        
        btn_install.clicked.connect(do_install)
        btn_cancel.clicked.connect(dialog.reject)
        
        btn_layout.addStretch()
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_install)
        layout.addLayout(btn_layout)
        
        dialog.exec()
    
    def check_iwads(self):
        """Step 3: Check installed IWADs."""
        self.clear_layout()
        self.step = 3
        
        title = QLabel("Step 2: Original Game Files (IWADs)")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        
        required_iwads = ["doom.wad", "doom2.wad", "heretic.wad", "hexen.wad", "plutonia.wad", "tnt.wad"]
        found_iwads = []
        missing_iwads = []
        info_text = ""

        # Case-insensitive check: compare against actual filesystem names
        existing_lower = set()
        if os.path.exists(cfg.IWAD_DIR):
            existing_lower = {f.lower() for f in os.listdir(cfg.IWAD_DIR)}

        for iwad in required_iwads:
            if iwad.lower() in existing_lower:
                found_iwads.append(iwad)
            else:
                missing_iwads.append(iwad)
        
        info_parts = [
            "Use the browse button to select one or more IWAD files from your system.",
            f"Selected files will be copied into: {cfg.IWAD_DIR}",
        ]

        if found_iwads:
            info_parts.append("\nDetected IWADs:")
            info_parts.extend([f"  • {i}" for i in found_iwads])
        
        if missing_iwads:
            info_parts.append("\nMissing IWADs:")
            info_parts.extend([f"  • {i}" for i in missing_iwads])
        else:
            info_parts.append("\nAll required IWADs are available.")

        info = QLabel("\n".join(info_parts))
        
        info.setWordWrap(True)
        
        hint = QLabel(
            "Hint: You can multi-select IWAD files in the file dialog. Supported files are usually *.wad."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #b8b8b8;")

        btn_browse_iwads = QPushButton("Browse IWAD Files...")
        btn_browse_iwads.clicked.connect(self.browse_iwads)

        btn_next = QPushButton("Finish ▶")
        btn_next.clicked.connect(self.finish_wizard)
        
        btn_install_later = QPushButton("Install Later")
        btn_install_later.clicked.connect(self.finish_wizard)
        
        self.layout.addWidget(title)
        self.layout.addWidget(info)
        self.layout.addWidget(hint)
        self.layout.addStretch()
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(btn_install_later)
        btn_layout.addWidget(btn_browse_iwads)
        btn_layout.addWidget(btn_next)
        self.layout.addLayout(btn_layout)

    def browse_iwads(self):
        """Select one or more IWAD files and copy them into the local iwad folder."""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select IWAD files",
            cfg.BASE_DIR,
            "WAD files (*.wad);;All files (*.*)",
        )

        if not files:
            return

        imported = []
        skipped = []
        failed = []

        for source_path in files:
            try:
                source_abs = os.path.abspath(source_path)
                target_path = os.path.join(cfg.IWAD_DIR, os.path.basename(source_path))
                target_abs = os.path.abspath(target_path)

                if source_abs == target_abs:
                    skipped.append(os.path.basename(source_path))
                    continue

                shutil.copy2(source_abs, target_abs)
                imported.append(os.path.basename(source_path))
            except Exception:
                failed.append(os.path.basename(source_path))

        summary = []
        if imported:
            summary.append("Imported:")
            summary.extend([f"  • {name}" for name in imported])
        if skipped:
            summary.append("\nSkipped (already in target folder):")
            summary.extend([f"  • {name}" for name in skipped])
        if failed:
            summary.append("\nFailed:")
            summary.extend([f"  • {name}" for name in failed])

        QMessageBox.information(
            self,
            "IWAD Import",
            "\n".join(summary) if summary else "No files were imported.",
        )

        # Auto-create starter map entries for newly imported IWADs
        for fname in imported:
            key = fname.lower()
            if key in _STARTER_MAPS:
                meta = _STARTER_MAPS[key]
                if not db.get_map_by_id(meta["ID"]):
                    db.insert_map({
                        "Cleared": "0",
                        "NoMods": "0",
                        "ID": meta["ID"],
                        "Name": meta["Name"],
                        "IWAD": meta["IWAD"],
                        "Path": "-",
                        "MOD": "0",
                        "ARGS": "0",
                        "Kategorie": "IWAD",
                        "Playtime": "0",
                        "LastPlayed": "-",
                        "RemoteID": "0",
                        "Favorite": "0",
                    })

        self.check_iwads()
    
    def finish_wizard(self):
        """Finish the wizard and remember completion state."""
        cfg.update_config_value("SETTINGS", "setup_completed", "1")
        self.wizard_complete.emit()
        self.accept()


def should_run_wizard() -> bool:
    """Return whether the setup wizard should run on startup."""
    try:
        completed = cfg.config.get("SETTINGS", "setup_completed", fallback="0")
        return completed == "0"
    except Exception:
        return True
