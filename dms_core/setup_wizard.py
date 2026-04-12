"""
Einrichtungsassistent für DMS beim ersten Start.
Prüft Engines und IWADs und leitet den Nutzer durch die Installation.
"""

import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QMessageBox, QCheckBox, QGroupBox, QScrollArea, QWidget
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

import dms_core.config as cfg
import dms_core.engine_manager as engines
import dms_core.initialization as init


class SetupWizard(QDialog):
    """Hauptassistent für die Ersteinrichtung."""
    
    wizard_complete = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        # Safety net: stellt Grundstruktur sicher, auch wenn GUI-Start ohne vorheriges Setup erfolgte.
        init.run_initial_setup()
        self.setWindowTitle("DMS - Einrichtungsassistent")
        self.setModal(True)
        self.resize(600, 400)
        self.step = 0
        
        self.layout = QVBoxLayout(self)
        self.show_welcome()
    
    def clear_layout(self):
        """Leert das aktuelle Layout für den nächsten Schritt."""
        while self.layout.count():
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
    
    def show_welcome(self):
        """Schritt 1: Willkommensbildschirm."""
        self.clear_layout()
        self.step = 1
        
        title = QLabel("Willkommen zu Doom Management System (D.M.S.)")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        
        info = QLabel(
            "Dieser Assistent hilft dir bei der Ersteinrichtung.\n\n"
            "Wir werden folgende Punkte prüfen:\n"
            "1. Game Engines (GZDoom, UZDoom, etc.)\n"
            "2. Original-Spiele (IWAD-Dateien)\n\n"
            "Klicke 'Weiter', um zu beginnen."
        )
        info.setWordWrap(True)
        
        btn_next = QPushButton("▶ Weiter")
        btn_next.clicked.connect(self.check_engines)
        
        btn_skip = QPushButton("Überspringen")
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
        """Schritt 2: Prüfe installierte Engines."""
        self.clear_layout()
        self.step = 2
        
        title = QLabel("Schritt 1: Game Engines")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        
        # Prüfe welche Engines existieren
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
            info_text += f"✅ Installierte Engines:\n" + \
                        "\n".join([f"  • {e.upper()}" for e in installed_engines])
        
        if missing_engines:
            if info_text:
                info_text += "\n\n"
            info_text += f"❌ Fehlende Engines:\n" + \
                        "\n".join([f"  • {e.upper()}" for e in missing_engines]) + \
                        "\n\nDu kannst sie jetzt installieren oder später."
        
        info = QLabel(info_text if info_text else "Keine Engines gefunden.")
        info.setWordWrap(True)
        
        # Button für Engine-Installation
        btn_install_engine = QPushButton("⬇ Engine installieren")
        btn_install_engine.clicked.connect(self.install_engine_dialog)
        
        btn_next = QPushButton("▶ Weiter")
        btn_next.clicked.connect(self.check_iwads)
        
        btn_skip = QPushButton("Überspringen")
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
        """Zeigt eine Auswahl von Engines zum Installieren."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Engine auswählen")
        dialog.resize(400, 300)
        layout = QVBoxLayout(dialog)
        
        title = QLabel("Wähle eine Engine zum Installieren:")
        title.setFont(QFont("Arial", 12, QFont.Bold))
        layout.addWidget(title)
        
        # Scroll-Area mit Checkboxen
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
                cb.setText(cb.text() + " (empfohlen)")
            self.engine_checkboxes[eng] = cb
            container_layout.addWidget(cb)
        
        container_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_install = QPushButton("Installieren")
        btn_cancel = QPushButton("Abbrechen")
        
        def do_install():
            selected = [eng for eng, cb in self.engine_checkboxes.items() if cb.isChecked()]
            if not selected:
                QMessageBox.warning(dialog, "Fehler", "Bitte wähle mindestens eine Engine aus!")
                return
            
            successful = []
            failed = []
            
            for eng in selected:
                success = engines.install_engine(eng)
                if success:
                    successful.append(eng)
                else:
                    failed.append(eng)
            
            successful_txt = ", ".join([e.upper() for e in successful]) if successful else "Keine"
            failed_txt = ", ".join([e.upper() for e in failed]) if failed else "Keine"
            
            if successful:
                QMessageBox.information(
                    dialog,
                    "Fertig",
                    f"Engine-Installation abgeschlossen!\n\nErfolgreich: {successful_txt}\n\nFehlgeschlagen: {failed_txt}",
                )
            else:
                QMessageBox.warning(dialog, "Fehler", "Alle Installationen sind fehlgeschlagen!")
            
            dialog.accept()
        
        btn_install.clicked.connect(do_install)
        btn_cancel.clicked.connect(dialog.reject)
        
        btn_layout.addStretch()
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_install)
        layout.addLayout(btn_layout)
        
        dialog.exec()
    
    def check_iwads(self):
        """Schritt 3: Prüfe installierte IWADs."""
        self.clear_layout()
        self.step = 3
        
        title = QLabel("Schritt 2: Original-Spiele (IWADs)")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        
        # Prüfe welche IWADs existieren
        required_iwads = ["doom.wad", "doom2.wad", "heretic.wad", "hexen.wad", "plutonia.wad", "tnt.wad"]
        found_iwads = []
        missing_iwads = []
        info_text = ""
        
        for iwad in required_iwads:
            path = os.path.join(cfg.IWAD_DIR, iwad)
            if os.path.exists(path):
                found_iwads.append(iwad)
            else:
                missing_iwads.append(iwad)
        
        if found_iwads:
            info_text = f"✅ Folgende IWADs gefunden:\n" + \
                       "\n".join([f"  • {i}" for i in found_iwads])
            info = QLabel(info_text)
        else:
            info = QLabel("")
        
        if missing_iwads:
            if info_text:
                info.setText(info.text() + "\n\n")
            else:
                info_text = ""
            
            missing_text = f"❌ Fehlende IWADs:\n" + \
                          "\n".join([f"  • {i}" for i in missing_iwads]) + \
                          "\n\n" + \
                          "Um diese zu installieren:\n" + \
                          "1. Lege die .wad Dateien in den 'Install' Ordner\n" + \
                          "2. Klicke auf '📥 Install Custom Maps' in der Haupt-GUI\n" + \
                          "3. Wähle die Dateien aus"
            
            info.setText(info.text() + missing_text)
        else:
            info.setText(info.text() + "\n\n✅ Alle IWADs vorhanden!")
        
        info.setWordWrap(True)
        
        btn_next = QPushButton("▶ Fertig")
        btn_next.clicked.connect(self.finish_wizard)
        
        btn_install_later = QPushButton("Später installieren")
        btn_install_later.clicked.connect(self.finish_wizard)
        
        self.layout.addWidget(title)
        self.layout.addWidget(info)
        self.layout.addStretch()
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(btn_install_later)
        btn_layout.addWidget(btn_next)
        self.layout.addLayout(btn_layout)
    
    def finish_wizard(self):
        """Beendet den Assistenten und merkt sich, dass Setup abgeschlossen ist."""
        # Speichere dass der Wizard durchlaufen wurde
        cfg.update_config_value("SETTINGS", "setup_completed", "1")
        self.wizard_complete.emit()
        self.accept()


def should_run_wizard() -> bool:
    """Prüft ob der Wizard beim Start ausgeführt werden soll."""
    try:
        completed = cfg.config.get("SETTINGS", "setup_completed", fallback="0")
        return completed == "0"
    except:
        return True
