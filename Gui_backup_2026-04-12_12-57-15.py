import sys
import os
import csv
import random
import logging
import traceback
import configparser

# Nur die Widgets, die wirklich im Code vorkommen
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTableWidget, QTableWidgetItem, 
    QVBoxLayout, QHBoxLayout, QPushButton, QWidget, QHeaderView, 
    QLabel, QMenu, QMessageBox, QDialog, QLineEdit, QCheckBox, 
    QGroupBox, QSplitter, QAbstractItemView, QScrollArea, QFrame, 
    QInputDialog
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QIcon, QColor, QFont

# ============================================================================
# CORE-MODULE IMPORTIEREN
# ============================================================================
import dms_core.config as cfg
import dms_core.database as db
import dms_core.engine_manager as engines
import dms_core.game_runner as runner
import dms_core.api as api
import dms_core.installer as installer
import dms_core.map_loader as loader
import dms_core.updater as updater
import dms_core.initialization as init
from dms_core.utils import tracker

# Error Logging Setup (Geräuschlos im Hintergrund)
logging.basicConfig(filename=os.path.join(cfg.BASE_DIR, 'dms_error.log'), level=logging.ERROR, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

# ============================================================================
# GLOBALER FANGZAUN (CRASH HANDLER)
# ============================================================================
def global_exception_handler(exc_type, exc_value, exc_traceback):
    """
    Fängt alle unbehandelten Fehler im gesamten Programm ab, 
    speichert sie im Log und zeigt eine Warnung in der GUI.
    """
    # 1. Den genauen Fehlertext (Traceback) zusammenbauen
    tb_lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
    tb_text = "".join(tb_lines)

    # 2. Unsichtbar in die dms_error.log schreiben
    logging.error(f"UNBEHANDELTER ABSTURZ:\n{tb_text}")
    print(f"[CRASH] Ein fataler Fehler ist aufgetreten. Siehe dms_error.log")

    # 3. Dem User ein schickes GUI-Fenster zeigen (falls die GUI schon läuft)
    app = QApplication.instance()
    if app:
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowTitle("Kritischer Systemfehler")
        msg.setText("Ein unerwarteter Fehler ist aufgetreten!\nDas Programm muss leider beendet werden.")
        msg.setInformativeText("Ein Bericht wurde in der 'dms_error.log' gespeichert.")
        msg.setDetailedText(tb_text) # Fügt den "Details..." Button hinzu
        msg.exec()

    # 4. Das Programm sicher beenden
    sys.exit(1)

# Den globalen Fangzaun im System aktivieren!
sys.excepthook = global_exception_handler

# ============================================================================
# DIALOGE (API, ENGINES, DETAILS)
# ============================================================================

class EngineManagerDialog(QDialog):
    """Dialog zur Verwaltung und zum Download von Source-Ports."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Engine Manager")
        self.resize(500, 400)
        self.layout = QVBoxLayout(self)
        
        self.info_label = QLabel("Hier kannst du Engines verwalten:")
        self.layout.addWidget(self.info_label)

        self.table = QTableWidget(0, 2) # Name und Status
        self.table.setHorizontalHeaderLabels(["Engine", "Status"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.layout.addWidget(self.table)
        self.table.setViewportMargins(0, 3, 0, 0)

        btn_layout = QHBoxLayout()
        self.btn_download = QPushButton("Installieren / Update")
        self.btn_set_active = QPushButton("Als Aktiv setzen")
        btn_layout.addWidget(self.btn_download)
        btn_layout.addWidget(self.btn_set_active)
        self.layout.addLayout(btn_layout)

        self.btn_download.clicked.connect(self.download_selected)
        self.btn_set_active.clicked.connect(self.set_active)

        self.load_engines()

    def get_engine_status(self, engine_name):
        """Prüft, ob die EXE im Engines-Ordner existiert."""
        path = engines.get_engine_path(engine_name)
        return "BEREIT" if os.path.exists(path) else "-"

    def load_engines(self):
        """Scannt alle unterstützten Engines und zeigt deren Status."""
        self.table.setRowCount(0)
        
        # Aktuellen Wert aus der Config frisch lesen
        import configparser
        config = configparser.ConfigParser()
        config.read(cfg.CONFIG_FILE, encoding="utf-8-sig")
        current_cfg = config.get("SETTINGS", "current_engine", fallback="")

        for row, eng in enumerate(cfg.SUPPORTED_ENGINES):
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(eng))
            
            status = self.get_engine_status(eng) # Prüft, ob EXE existiert
            status_item = QTableWidgetItem(status)
            
            # Markierung der AKTIVEN Engine
            # Nur markieren, wenn der Name übereinstimmt UND nicht leer ist
            if current_cfg and eng.lower() == current_cfg.lower():
                status_item.setText(f"AKTIV ({status})")
                color = QColor(46, 204, 113) if status == "BEREIT" else QColor(231, 76, 60)
                status_item.setBackground(color)
            
            self.table.setItem(row, 1, status_item)

    # In Gui.py innerhalb der Klasse EngineManagerDialog

    def set_active(self):
        row = self.table.currentRow()
        if row < 0: return
        eng_name = self.table.item(row, 0).text()
        
        # 1. Datei einlesen
        config = configparser.ConfigParser()
        config.read(cfg.CONFIG_FILE, encoding="utf-8-sig")
        
        # 2. Sektion sicherstellen
        if not config.has_section("SETTINGS"):
            config.add_section("SETTINGS")
            
        # 3. Wert setzen
        config.set("SETTINGS", "current_engine", eng_name)
        
        # 4. Speichern mit utf-8-sig (damit config.py es sicher lesen kann)
        with open(cfg.CONFIG_FILE, "w", encoding="utf-8-sig") as f:
            config.write(f)
            
        # 5. Globalen Wert im Speicher aktualisieren
        cfg.CURRENT_ENGINE = eng_name
        
        # 6. UI-Feedback
        self.load_engines()
        if self.parent():
            self.parent().refresh_data()
            
        QMessageBox.information(self, "Erfolg", f"{eng_name} ist jetzt aktiv.")

    def download_selected(self):
        """Nutzt den engine_manager zum Download."""
        row = self.table.currentRow()
        if row < 0: return
        eng_name = self.table.item(row, 0).text()
        
        self.info_label.setText(f"Downloade {eng_name}...")
        QApplication.processEvents()
        
        # Hier rufen wir deine Funktion aus dem engine_manager auf
        success = engines.install_engine(eng_name, callback=lambda m: self.info_label.setText(m))
        if success:
            QMessageBox.information(self, "Erfolg", f"{eng_name} wurde installiert.")
            self.load_engines()
        else:
            QMessageBox.critical(self, "Fehler", "Download fehlgeschlagen.")


class ApiBrowserDialog(QDialog):
    main_refresh_signal = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Doomworld (idgames) Browser")
        self.resize(950, 700)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # --- SUCHE ---
        search_layout = QHBoxLayout()
        search_layout.setContentsMargins(5, 5, 5, 5)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Suchbegriff eingeben...")
        self.btn_search = QPushButton("Suchen")
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.btn_search)
        self.layout.addLayout(search_layout)

        # --- SHORTCUTS (Synchronisiert mit deiner api.py) ---
        shortcut_group = QGroupBox("Top Megawads / Levels")
        shortcut_layout = QHBoxLayout()
        shortcut_layout.setContentsMargins(5, 5, 5, 5)
        
        # WICHTIG: Die zweiten Werte müssen exakt so heißen wie in deiner api.py!
        self.shortcuts = [
            ("Doom 1", "doom_megawads"),
            ("Doom 2", "doom2_megawads"),
            ("Heretic", "heretic"),
            ("Hexen", "hexen")
        ]

        for label, cat in self.shortcuts:
            btn = QPushButton(label)
            btn.clicked.connect(lambda checked=False, c=cat: self.load_top(c))
            shortcut_layout.addWidget(btn)
        
        shortcut_group.setLayout(shortcut_layout)
        shortcut_group.setStyleSheet("QGroupBox { margin: 0px; padding: 0px; }")
        self.layout.addWidget(shortcut_group)

        # --- TABELLE ---
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Titel", "Größe", "Rating", "Status"])
        
        # Header-Design
        self.table.horizontalHeader().setFixedHeight(38)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, 4):
            self.table.horizontalHeader().setSectionResizeMode(i, QHeaderView.Fixed)
            self.table.setColumnWidth(i, 110)
        self.table.horizontalHeader().setStyleSheet("""
            QHeaderView {
                background-color: transparent; 
                border: none;
                margin-bottom: 2px;
            }
            QHeaderView::section {
                background-color: #252525;
                color: #aaaaaa;
                padding: 6px;
                border: none;
                font-weight: bold;
            }
        """)
            
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setContentsMargins(0, 0, 0, 0)
        self.layout.addWidget(self.table)

        # --- DOWNLOAD & STATUS ---
        self.btn_download = QPushButton("Ausgewählte Mod Herunterladen")
        self.btn_download.setMinimumHeight(45)
        self.btn_download.setEnabled(False)
        self.btn_download.setStyleSheet("background-color: #2980b9; color: white; font-weight: bold;")
        self.layout.addWidget(self.btn_download)

        self.status_bottom = QLabel("Bereit.")
        self.status_bottom.setContentsMargins(5, 5, 5, 5)
        self.layout.addWidget(self.status_bottom)

        # Connections
        self.btn_search.clicked.connect(self.perform_search)
        self.search_input.returnPressed.connect(self.perform_search)
        self.table.itemSelectionChanged.connect(lambda: self.btn_download.setEnabled(True))
        self.btn_download.clicked.connect(self.download_map)
        
        self.current_results = []

    def load_top(self, category):
        self.status_bottom.setText(f"Lade Top-Einträge für {category}...")
        self.table.setRowCount(0)
        QApplication.processEvents()
        
        try:
            # Jetzt mit detaillierter Fehler-Rückgabe
            self.current_results = api.get_top_wads(category, callback=lambda msg: self.status_bottom.setText(msg))
            self.populate_table()
        except Exception as e:
            # Hier zeigen wir jetzt den echten Fehler an!
            error_type = type(e).__name__
            self.status_bottom.setText(f"❌ API-Fehler ({error_type}): {str(e)[:50]}...")
            print(f"[GUI DEBUG] Detailierter Fehler: {traceback.format_exc()}")

    def perform_search(self):
        query = self.search_input.text().strip()
        if not query: return
        self.status_bottom.setText(f"Suche nach '{query}'...")
        QApplication.processEvents()
        self.current_results = api.search_idgames(query)
        self.populate_table()

    def populate_table(self):
        
        # 1. Signale blockieren, um Endlosschleifen/Spam zu verhindern
        self.table.blockSignals(True)
        
        try:
            self.table.setRowCount(0)
            self.status_bottom.setText(f"Verarbeite {len(self.current_results)} Ergebnisse...")
            
            for row, res in enumerate(self.current_results):
                self.table.insertRow(row)
                
                # Daten aus dem API-Resultat holen
                title = res.get("title") or res.get("filename", "Unknown")
                size_mb = f"{int(res.get('size', 0)) / (1024*1024):.1f} MB"
                rating = f"{float(res.get('rating', 0) or 0):.1f} ★"
                is_installed = res.get("is_installed", False)
                
                # Items erstellen
                display_title = f"✓ {title}" if is_installed else str(title)
                item_title = QTableWidgetItem(display_title)
                item_title.setData(Qt.UserRole, res)
                
                item_size = QTableWidgetItem(size_mb)
                item_size.setTextAlignment(Qt.AlignCenter)
                
                item_rating = QTableWidgetItem(rating)
                item_rating.setTextAlignment(Qt.AlignCenter)
                
                status_text = "INSTALLED" if is_installed else "-"
                item_status = QTableWidgetItem(status_text)
                item_status.setTextAlignment(Qt.AlignCenter)

                # Styling nur anwenden, wenn installiert
                if is_installed:
                    green = QColor(46, 204, 113)
                    bold_font = QFont("Arial", 9, QFont.Bold)
                    
                    item_title.setForeground(green)
                    item_status.setForeground(green)
                    item_status.setFont(bold_font)

                # Jedes Item GENAU EINMAL setzen
                self.table.setItem(row, 0, item_title)
                self.table.setItem(row, 1, item_size)
                self.table.setItem(row, 2, item_rating)
                self.table.setItem(row, 3, item_status)

        finally:
            # Signale wieder freigeben
            self.table.blockSignals(False)
            self.status_bottom.setText(f"{len(self.current_results)} Ergebnisse gefunden.")

    def download_map(self):
        row = self.table.currentRow()
        if row < 0: return
        file_data = self.current_results[row]
        
        self.status_bottom.setText(f"Downloade: {file_data.get('title')}...")
        self.btn_download.setEnabled(False)
        QApplication.processEvents()
        
        success, msg = api.download_idgames_gui(file_data, callback=lambda t: self.status_bottom.setText(t))
        
        if success:
            QMessageBox.information(self, "Erfolg", f"Download abgeschlossen!\nID: {msg}")
            self.main_refresh_signal.emit() # Refresht die Haupt-GUI Tabelle
            self.populate_table() # Setzt den Status auf INSTALLED
        else:
            QMessageBox.critical(self, "Fehler", f"Download fehlgeschlagen:\n{msg}")
        
        self.btn_download.setEnabled(True)


# ============================================================================
# HAUPT-GUI (D.M.S. SCHALTZENTRALE)
# ============================================================================

class DoomManagerGUI(QMainWindow):
    signal_refresh = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Doom Management System (D.M.S.) v{cfg.APP_VERSION}")
        self.resize(1200, 800)
        
        self.all_maps_data = []
        self.signal_refresh.connect(self.refresh_data)

        self.setup_ui()
        self.refresh_data()
        
        # Check für Updates beim Start
        self.check_updates()

    def setup_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        # --- TOP BAR (Stats & Buttons oben rechts) ---
        top_layout = QHBoxLayout()
        
        self.btn_api = QPushButton("🌐 Doomworld")
        self.btn_eng = QPushButton("⚙️ Engine Manager")
        self.btn_install = QPushButton("📥 Install Custom Maps")

        # Signale verknüpfen
        self.btn_api.clicked.connect(self.open_api)
        self.btn_eng.clicked.connect(self.open_eng)
        self.btn_install.clicked.connect(self.run_installer)
        
        top_layout.addStretch() # Schiebt alles nach rechts
        top_layout.addWidget(self.btn_install)
        top_layout.addWidget(self.btn_api)
        top_layout.addWidget(self.btn_eng)
        layout.addLayout(top_layout)

        # --- SPLITTER (Tabelle Links, Panel Rechts) ---
        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter)

        # 1. TABELLE (Links im Splitter)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["", "", ""])
        self.table.horizontalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectItems) 
        
        # --- NEU: 3D-BUTTON STYLING ---
        self.table.setShowGrid(False) # Versteckt die klassischen Excel-Linien
        self.table.verticalHeader().setDefaultSectionSize(42) # Gibt den Buttons genug Höhe
        
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #1e1e1e;
                border: none;
                padding: 5px;
            }
            
            QTableWidget::item:disabled {
                background-color: transparent;
                border: none;
            }

            QTableWidget::item {
                background-color: #2b2b2b;
                border: 1px solid #3a3a3a;
                border-bottom: 4px solid #111111;
                border-radius: 6px;
                margin: 3px 6px;
                padding: 8px 15px 4px 15px;
                
                /* --- HIER IST DIE MAGIE FÜR DEN TEXT --- */
                color: #ffffff;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 14px;
                font-weight: bold;
            }
            
            QTableWidget::item:hover {
                background-color: #353535;
                border: 1px solid #4a4a4a;
                border-bottom: 4px solid #000000;
            }
            
            QTableWidget::item:selected {
                background-color: #4a4a4a;
                border: 1px solid #666666;
                border-bottom: 2px solid #111111;
                margin-top: 5px;
                color: white;
            }
        """)
        # ------------------------------

        # Signale für die Tabelle
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        self.table.itemDoubleClicked.connect(self.run_selected_map)

        header_container = QWidget()
        header_layout = QHBoxLayout(header_container)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(0)

        lbl_doom_header = QLabel("Doom Maps")
        lbl_doom_header.setAlignment(Qt.AlignCenter)
        lbl_doom_header.setStyleSheet(
            "color: #ecf0f1; font-weight: bold; font-size: 14px;"
            " background-color: #2c3e50; padding: 10px 0; border: 1px solid #3a3a3a;"
        )

        lbl_heretic_header = QLabel("Heretic / Hexen / Extras")
        lbl_heretic_header.setAlignment(Qt.AlignCenter)
        lbl_heretic_header.setStyleSheet(
            "color: #ecf0f1; font-weight: bold; font-size: 14px;"
            " background-color: #2c3e50; padding: 10px 0; border: 1px solid #3a3a3a;"
        )

        header_layout.addWidget(lbl_doom_header, 2)
        header_layout.addWidget(lbl_heretic_header, 1)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        left_layout.addWidget(header_container)
        left_layout.addWidget(self.table)

        splitter.addWidget(left_panel)

        # 2. RECHTES PANEL (Mods & Start-Button)
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 0, 10, 10) # Etwas Rand für eine sauberere Optik
        
        # --- Mod-Auswahl Box mit Scroll-Area ---
        mod_group = QGroupBox("Verfügbare Mods")
        # Styling: margin-top etwas verringert, padding-top komplett entfernt
        mod_group.setStyleSheet("""
            QGroupBox { font-weight: bold; border: 1px solid #555; border-radius: 5px; margin-top: 8px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; color: #aaa; }
        """)
        
        # Das Container-Widget
        mod_container = QWidget()
        self.mod_layout = QVBoxLayout(mod_container)
        self.mod_layout.setAlignment(Qt.AlignTop) 
        self.mod_layout.setSpacing(2) # Checkboxen noch einen Hauch enger
        self.mod_layout.setContentsMargins(5, 5, 5, 5) # Zwingt das innere Layout ganz an den Rand
        
        # Die Scroll-Area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(mod_container)
        scroll_area.setFrameShape(QScrollArea.NoFrame) # Entfernt den unsichtbaren Rahmen der Scrollbox
        scroll_area.setStyleSheet("QScrollArea { background: transparent; }")
        
        # Scroll-Area in die GroupBox packen
        group_layout = QVBoxLayout()
        # HIER IST DER TRICK: Nimmt der Box den Standard-Abstand nach oben (vorher ca. 15px, jetzt 8px)
        group_layout.setContentsMargins(2, 8, 2, 2) 
        group_layout.addWidget(scroll_area)
        mod_group.setLayout(group_layout)
        
        right_layout.addWidget(mod_group)
        
        # Mods in das neue Layout laden
        self.populate_mods() 
        
        # Abstandhalter (schiebt die Buttons nach unten)
        right_layout.addSpacing(10)

        # --- Buttons & Controls ---
        self.cb_debug = QCheckBox("🛠 Debug-Modus (Vorschau)")
        self.cb_debug.setStyleSheet("color: #e67e22; font-weight: bold;")
        right_layout.addWidget(self.cb_debug)

        self.btn_random = QPushButton("🎲 ZUFALLSKARTE")
        self.btn_random.setMinimumHeight(40)
        self.btn_random.clicked.connect(self.play_random)
        right_layout.addWidget(self.btn_random)

        self.btn_run = QPushButton("▶ SPIEL STARTEN")
        self.btn_run.setMinimumHeight(60)
        self.btn_run.setStyleSheet("""
            QPushButton { background-color: #27ae60; color: white; font-weight: bold; font-size: 14px; border-radius: 4px; }
            QPushButton:hover { background-color: #2ecc71; }
            QPushButton:pressed { background-color: #219653; }
        """)
        self.btn_run.clicked.connect(self.run_selected_map)
        right_layout.addWidget(self.btn_run)

        splitter.addWidget(right_panel)
        
        # --- DER BREITEN-FIX ---
        # Größenverhältnis anpassen: Wir geben der Tabelle links 950px und dem Panel rechts nur noch 250px!
        splitter.setSizes([950, 250])

        self.statusBar().showMessage("Bereit.")

        # --- STATUS BAR (Ganz unten) ---
    
        # --- DASHBOARD PANEL ---
        self.stats_panel = QFrame()
        self.stats_panel.setObjectName("Dashboard")
        self.stats_panel.setFixedHeight(35)
        self.stats_panel.setStyleSheet("background-color: #252525; border-top: 1px solid #444;")
        
        stats_layout = QHBoxLayout(self.stats_panel)
        stats_layout.setContentsMargins(15, 0, 15, 0)

        # WICHTIG: Überall muss "self." davor stehen!
        self.stat_count = QLabel("📂 KARTEN: -")
        self.stat_cleared = QLabel("✅ CLEAR: -")
        self.stat_cleared.setStyleSheet("color: #2ecc71;") 
        self.stat_playtime = QLabel("🕒 ZEIT: -")
        self.stat_engine = QLabel("⚙️ ENGINE: -")

        def get_sep():
            sep = QLabel("|")
            sep.setStyleSheet("color: #444;")
            return sep

        # Zum Layout hinzufügen
        stats_layout.addWidget(self.stat_count)
        stats_layout.addWidget(get_sep())
        stats_layout.addWidget(self.stat_cleared)
        stats_layout.addWidget(get_sep())
        stats_layout.addWidget(self.stat_playtime)
        stats_layout.addWidget(get_sep())
        stats_layout.addWidget(self.stat_engine)
        stats_layout.addStretch()

        layout.addWidget(self.stats_panel)

        self.update_stats()

    def populate_mods(self):
        """Lädt alle Mods sortiert nach Kategorien und baut das Menü auf."""
        # Kategorien definieren (Titel in der GUI : Ordnername im Dateisystem)
        categories = {
            "DOOM MODS": "doom",
            "HERETIC MODS": "heretic",
            "HEXEN MODS": "hexen"
        }

        has_any_mods = False

        for title, folder_name in categories.items():
            mod_dir = os.path.join(cfg.BASE_DIR, "mods", folder_name)
            
            # Überspringen, falls der Ordner gar nicht existiert
            if not os.path.exists(mod_dir):
                continue

            # Finde alle Unterordner (Mods) in diesem Verzeichnis
            mod_folders = [d for d in os.listdir(mod_dir) if os.path.isdir(os.path.join(mod_dir, d))]

            # Wenn der Ordner leer ist, überspringen wir die Kategorie komplett!
            if not mod_folders:
                continue

            has_any_mods = True

            # 1. HEADER ERSTELLEN (Mit den perfekten Abständen)
            header = QLabel(title)
            if self.mod_layout.count() == 0:
                # Erstes Element: Kein Abstand nach oben
                header.setStyleSheet("font-weight: bold; color: #3498db; margin-bottom: 2px;")
            else:
                # Alle weiteren Kategorien: Etwas Abstand nach oben zur Trennung
                header.setStyleSheet("font-weight: bold; color: #3498db; margin-top: 15px; margin-bottom: 2px;")
                
            self.mod_layout.addWidget(header)

            # 2. DIE CHECKBOXEN ERSTELLEN (Die waren vorher verschwunden!)
            for mod in sorted(mod_folders):
                cb = QCheckBox(mod)
                
                # Wir speichern den genauen, absoluten Pfad unsichtbar in der Checkbox
                full_path = os.path.join(mod_dir, mod)
                cb.setProperty("mod_path", full_path)
                
                self.mod_layout.addWidget(cb)

        # Fallback, falls absolut gar keine Mods installiert sind
        if not has_any_mods:
            lbl_empty = QLabel("Keine Mods installiert.")
            lbl_empty.setStyleSheet("color: gray; font-style: italic;")
            self.mod_layout.addWidget(lbl_empty)

    def load_data(self):
        """Liest die CSV-Datei ein."""
        self.all_maps_data = []
        if not os.path.exists(cfg.CSV_FILE): return

        with open(cfg.CSV_FILE, "r", encoding="utf-8-sig") as f:
            first_line = f.readline()
            delim = ";" if ";" in first_line else ","
            f.seek(0)
            reader = csv.DictReader(f, delimiter=delim)
            for row in reader:
                self.all_maps_data.append(row)

    def get_checked_mods(self):
        """Durchsucht das Mod-Layout und gibt eine Liste der markierten Mod-Pfade zurück."""
        selected_mods = []
        
        # Gehe alle Elemente im mod_layout durch (Header Labels UND Checkboxen)
        for i in range(self.mod_layout.count()):
            widget = self.mod_layout.itemAt(i).widget()
            
            # Ignoriert die Header-Labels automatisch, weil wir nur nach QCheckBox fragen
            if isinstance(widget, QCheckBox) and widget.isChecked():
                
                # Wir holen uns den unsichtbar gespeicherten Pfad
                mod_path = widget.property("mod_path")
                
                if mod_path:
                    selected_mods.append(mod_path)
                
        return selected_mods

    @tracker
    def run_selected_map(self, item=None):
        """Startet die gewählte Karte mit Berücksichtigung von Mod-Sperren und Debug-Modus."""
        # 1. Zelle ermitteln (Entweder übergebenes Item oder aktuell markierte Zelle)
        cell = item if item else self.table.currentItem()
        if not cell:
            QMessageBox.warning(self, "Abbruch", "Bitte wähle erst eine Karte aus der Liste aus!")
            return

        # 2. ID und Kartendaten laden
        mid = cell.data(Qt.UserRole)
        if not mid:
            QMessageBox.warning(self, "Fehler", "Konnte die ID der Karte nicht erkennen.")
            return

        map_data = db.get_map_by_id(mid)
        if not map_data:
            QMessageBox.critical(self, "Fehler", "Daten zur Karte konnten nicht geladen werden.")
            return

        # 3. Engine-Check (Live-Abfrage aus der Config statt alter Variable)
        active_engine_name = cfg.get_current_engine()
        
        if not active_engine_name:
            QMessageBox.critical(self, "Fehler", "Keine Engine ausgewählt! Geh in den Engine-Manager und aktiviere einen Port.")
            return

        # Pfad zur Engine-EXE dynamisch bauen (Engines/[Name]/[Name].exe)
        engine_path = os.path.join(cfg.ENGINE_BASE_DIR, active_engine_name, f"{active_engine_name}.exe")
        
        if not os.path.exists(engine_path):
            QMessageBox.critical(self, "Fehler", f"Die Engine-Datei wurde nicht gefunden:\n{engine_path}")
            return

        try:
            # 4. Mods verarbeiten
            selected_mods = self.get_checked_mods()
            
            # Prüfung der Mod-Sperre
            is_mod_locked = str(map_data.get('NoMods', '0')) == "1"
            if is_mod_locked:
                print(f"🚫 MOD-SPERRE AKTIV für {map_data.get('Name')}")
                selected_mods = []

            # 5. Start-Kommando generieren (über den Runner)
            debug_info = runner.get_start_command(engine_path, map_data, selected_mods)
            
            # 6. Optionales Debug-Menü
            if self.cb_debug.isChecked():
                cmd_str = ' '.join(debug_info.get('cmd', []))
                
                # Status-Anzeige für das Debug-Fenster
                mod_status_text = (
                    "<span style='color: #e74c3c;'>DEAKTIVIERT (Mod-Sperre aktiv)</span>" 
                    if is_mod_locked else f"<span style='color: #2ecc71;'>{len(selected_mods)} geladen</span>"
                )
                
                debug_msg = (
                    f"<b>ENGINE:</b><br>{active_engine_name}<br><br>"
                    f"<b>BEFEHL (CMD):</b><br><code style='color: #2ecc71;'>{cmd_str}</code><br><br>"
                    f"<b>MOD-STATUS:</b> {mod_status_text}<br><br>"
                    f"<b>DEINE PARAMETER (ARGS):</b><br><span style='color: #e74c3c;'>{map_data.get('ARGS', '-')}</span>"
                )
                
                msg_box = QMessageBox(self)
                msg_box.setWindowTitle("DMS Debug Menu")
                msg_box.setTextFormat(Qt.TextFormat.RichText)
                msg_box.setText(debug_msg)
                msg_box.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
                msg_box.button(QMessageBox.StandardButton.Ok).setText("Starten")
                
                if msg_box.exec() == QMessageBox.StandardButton.Cancel:
                    return

            # 7. Spiel tatsächlich ausführen
            print(f"🚀 Starte Spiel: {map_data.get('Name')} mit Engine: {active_engine_name}...")
            success = runner.run_game(engine_path, map_data, selected_mods)

            if success:
                self.update_stats()
            else:
                QMessageBox.warning(self, "Start fehlgeschlagen", "Das Spiel konnte nicht gestartet werden. Prüfe die Konsole/Logs.")

        except Exception as e:
            print(f"❌ CRASH in run_selected_map: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Crash", f"Fehler beim Startversuch:\n{str(e)}")

    def show_context_menu(self, pos):
        """Erstellt ein sauberes Rechtsklick-Menü ohne Geister-Effekte."""
        item = self.table.itemAt(pos)
        if not item: return
        
        mid = item.data(Qt.UserRole)
        if not mid: return

        # 1. Ein frisches, leeres Menü erstellen
        menu = QMenu(self.table)
        
        # 2. Exakt 4 Aktionen hinzufügen (OHNE triggered.connect!)
        act_clear = menu.addAction("✔ Map Clear")
        act_mod   = menu.addAction("🅼 Skip Mods")
        menu.addSeparator()
        act_args  = menu.addAction("🛠 Parameter bearbeiten (ARGS)")
        act_del   = menu.addAction("🗑 Map löschen")

        # 3. Menü anzeigen und warten, bis der User klickt.
        action = menu.exec(self.table.mapToGlobal(pos))

        # 4. ERST JETZT, wo das Menü sicher zu ist, führen wir die Befehle aus:
        if action == act_clear:
            db.toggle_map_clear(mid)
            self.refresh_data()
            
        elif action == act_mod:
            db.toggle_mod_skip(mid)
            self.refresh_data()
            
        elif action == act_args:
            # Hier rufen wir deine Parameter-Funktion auf
            if hasattr(self, 'edit_map_args'):
                self.edit_map_args(mid)
            elif hasattr(self, 'edit_args'): # Falls sie bei dir anders heißt
                self.edit_args(mid)
                
        elif action == act_del:
            self.delete_map(mid)

    def edit_map_parameters(self, row=None):
        
        # Die exakt angeklickte Zelle holen
        current_cell = self.table.currentItem()
        if not current_cell: 
            return
            
        map_id = current_cell.data(Qt.UserRole)
        if not map_id:
            return
            
        map_data = db.get_map_by_id(map_id)
        selected_mods = self.get_checked_mods()
        
        # Prüfen, ob die Mod-Sperre auf '1' steht
        if str(map_data.get('NoMods', '0')) == "1":
            print("🚫 MOD-SPERRE: Starte ohne Mods.")
            selected_mods = []
        if not map_data:
            return
            
        current_args = map_data.get('ARGS', '')
        map_name = map_data.get('Name', 'Unbekannt')

        # Eingabedialog öffnen
        new_args, ok = QInputDialog.getText(
            self, "Parameter definieren", 
            f"Zusätzliche Start-Parameter für '{map_name}':",
            QLineEdit.EchoMode.Normal, current_args
        )

        if ok:
            if hasattr(db, 'update_map_args'):
                db.update_map_args(map_id, new_args)
                QMessageBox.information(self, "Gespeichert", f"Parameter wurden aktualisiert:\n{new_args}")
                self.refresh_data()
            else:
                QMessageBox.warning(self, "Fehler", "Die Speicherfunktion fehlt in database.py!")

    def create_item(self, m):
            # 1. Ist die Zelle komplett leer? -> Unsichtbarer Button
            if not m: 
                item = QTableWidgetItem("")
                item.setFlags(Qt.ItemFlag.NoItemFlags) 
                return item
            
            # 2. Daten flexibel auslesen (Zweisprachig: Dictionary & Liste)
            try:
                if isinstance(m, dict) or hasattr(m, "keys"):
                    # Wenn die Daten als Dictionary kommen (Neues System)
                    c_flag = str(m.get("Cleared", "0")).strip()
                    m_flag = str(m.get("NoMods", "0")).strip()
                    mid    = str(m.get("ID", "")).strip().upper()
                    name   = str(m.get("Name", "")).strip()
                    iwad   = str(m.get("IWAD", "")).strip().lower()
                    f_flag = str(m.get("Favorite", "0")).strip()
                else:
                    # Wenn die Daten als Liste kommen (Altes System)
                    if len(m) < 4:
                        raise ValueError("Zu wenig Daten")
                    c_flag = str(m[0]).strip()
                    m_flag = str(m[1]).strip()
                    mid    = str(m[2]).strip().upper() 
                    name   = str(m[3]).strip()
                    iwad   = str(m[4]).strip().lower()
                    f_flag = str(m[12]).strip() if len(m) > 12 else "0"
            except (KeyError, IndexError, ValueError):
                # Falls eine Trennzeile verarbeitet wird -> Unsichtbar machen
                item = QTableWidgetItem("")
                item.setFlags(Qt.ItemFlag.NoItemFlags) 
                return item

            # Letzter Check: Wenn keine ID da ist -> Unsichtbar
            if not mid:
                item = QTableWidgetItem("")
                item.setFlags(Qt.ItemFlag.NoItemFlags) 
                return item

            # ==========================================
            # AB HIER GEHT DEIN DESIGN-CODE WEITER
            # ==========================================
            display = name if name and name != "-" else mid
            
            symbols = []
            if f_flag == "1": symbols.append("⭐")
            if c_flag == "1": symbols.append("✅")
            if m_flag == "1": symbols.append("🅼")
            
            if symbols:
                display = f"{display}   {' '.join(symbols)}"

            item = QTableWidgetItem(display)
            item.setData(Qt.UserRole, mid)
            item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

            if f_flag == "1":
                item.setForeground(QColor("#FFD700")) 
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            elif "hexen" in iwad:
                item.setForeground(QColor(155, 89, 182))
            elif "heretic" in iwad:
                item.setForeground(QColor(241, 196, 15))
            elif c_flag == "1":
                item.setForeground(QColor(46, 204, 113))

            return item

    def refresh_data(self):
        """Aktualisiert die Kartentabelle mit den Daten aus der Datenbank."""
        self.load_data()
        
        try:
            # 1. Daten aus der Datenbank holen
            all_m = db.get_all_maps()
            
            # 2. Karten verteilen & sortieren
            blocks = {1: [], 2: [], 3: []}
            doom_maps = []
            
            # Listen für die Extras (Spalte 3)
            heretic_maps = []
            hexen_maps = []
            strife_maps = []

            for m in all_m:
                # IWAD sicher auslesen (Zweisprachig für Dict & Liste)
                iwad = str(m.get("IWAD", "")).lower() if isinstance(m, dict) else str(m[4]).lower()
                
                # Fein-Sortierung für Spalte 3 (Extras)
                if "heretic" in iwad:
                    heretic_maps.append(m)
                elif "hexen" in iwad:
                    hexen_maps.append(m)
                elif "strife" in iwad:
                    strife_maps.append(m)
                else:
                    # Alles andere (Doom 1, Doom 2, Plutonia, TNT) ist DOOM
                    doom_maps.append(m)

            # --- SPALTE 3 ZUSAMMENBAUEN (MIT UNSICHTBAREN LÜCKEN) ---
            if heretic_maps:
                blocks[3].extend(heretic_maps)
                
            if hexen_maps:
                # Fügt eine leere Liste [] als Platzhalter ein, falls schon Heretic-Karten da sind
                if blocks[3]: 
                    blocks[3].append([]) 
                blocks[3].extend(hexen_maps)
                
            if strife_maps:
                # Fügt noch eine Lücke ein, falls es Strife gibt und vorher schon Karten da sind
                if blocks[3]:
                    blocks[3].append([])
                blocks[3].extend(strife_maps)
            # --------------------------------------------------------

            # Doom-Karten fair auf Spalte 1 und 2 aufteilen
            half = (len(doom_maps) + 1) // 2
            blocks[1] = doom_maps[:half]
            blocks[2] = doom_maps[half:]

            # 3. Maximale Zeilen berechnen
            max_rows = max(len(blocks[1]), len(blocks[2]), len(blocks[3]))
            self.table.setRowCount(max_rows)

            # 4. Tabelle füllen
            for i in range(max_rows):
                item1 = self.create_item(blocks[1][i]) if i < len(blocks[1]) else self.create_item([])
                item2 = self.create_item(blocks[2][i]) if i < len(blocks[2]) else self.create_item([])
                item3 = self.create_item(blocks[3][i]) if i < len(blocks[3]) else self.create_item([])
                
                self.table.setItem(i, 0, item1)
                self.table.setItem(i, 1, item2)
                self.table.setItem(i, 2, item3)

        except Exception as e:
            print(f"Fehler beim Laden der Tabelle: {e}")

    def update_stats(self):
        """Dashboard-Update (0/1 System)."""
        try:
            all_m = db.get_all_maps()
            total = len(all_m)
            cleared = sum(1 for m in all_m if str(m.get("Cleared", "0")) == "1")
            
            if hasattr(self, 'stat_count'):
                self.stat_count.setText(f"📂 KARTEN: {total}")
                self.stat_cleared.setText(f"✅ CLEAR: {cleared}")
                
                total_sec = db.get_total_seconds()
                h, r = divmod(int(total_sec), 3600)
                m, _ = divmod(r, 60)
                self.stat_playtime.setText(f"🕒 ZEIT: {h}H {m}M")
                
                eng = str(cfg.CURRENT_ENGINE).upper() if cfg.CURRENT_ENGINE else "NONE"
                self.stat_engine.setText(f"⚙️ ENGINE: {eng}")
        except Exception as e:
            print(f"❌ Statistik-Fehler: {e}")

    def get_selected_id(self):
        """Holt die versteckte ID aus der aktuell gewählten Zelle."""
        item = self.table.currentItem()
        if item:
            return item.data(Qt.UserRole)
        return None

    def on_cell_double_clicked(self, row, column):
        """Startet das Spiel bei Doppelklick auf eine Zelle."""
        map_id = self.get_selected_id()
        if map_id:
            self.run_game(map_id)

# ============================================================================
# KERN-FUNKTIONEN (SPIELEN & INSTALLIEREN)
# ============================================================================

    def run_game(self, map_id):
        """Startet das Spiel über den Runner und wertet die Session aus."""
        if not map_id: return
        
        # 1. Daten der Map finden
        r = next((m for m in self.all_maps_data if m['ID'] == map_id), None)
        if not r: return

        # 2. Mods aus GUI Checkboxen auslesen
        selected_mods = []
        for i in range(self.mod_layout.count()):
            item = self.mod_layout.itemAt(i)
            if item:
                widget = item.widget()
                if isinstance(widget, QCheckBox) and widget.isChecked():
                    selected_mods.append(widget.text())

        # 3. Vorbereitung der GUI
        self.statusBar().showMessage(f"Starte {r['Name']}...")
        self.hide() # Launcher verstecken, während wir zocken
        
        try:
            # 4. Der Aufruf an den Runner
            # WICHTIG: Erledigt Check, Start und Analyse in einem Rutsch
            result = runner.run_game(map_id, selected_mods=selected_mods)
            
            # 5. Launcher nach dem Spiel wieder zeigen
            self.show()
            
            # 6. Fehlerprüfung (z.B. wenn die Engine.exe fehlt)
            if isinstance(result, dict) and result.get("error"):
                QMessageBox.critical(self, "Startfehler", result.get("msg"))
                return

            # 7. Post-Game Auswertung (nur wenn länger als 5 Sek gespielt wurde)
            duration = result.get('duration_seconds', 0) if result else 0
            
            if duration > 5:
                # Statistiken in der Tabelle aktualisieren
                self.refresh_data() 
                
                m, s = divmod(duration, 60)
                stats = result.get('stats', {})
                weapons = result.get('weapons', [])
                
                msg = (f"Spielzeit: {m} Min. {s} Sek.\n\n"
                       f"GESAMMELT:\n"
                       f"✚ Heilung: {stats.get('health', 0)}  |  🛡 Rüstung: {stats.get('armor', 0)}\n"
                       f"📦 Munition: {stats.get('ammo', 0)}  |  🔑 Schlüssel: {stats.get('key', 0)}\n\n"
                       f"WAFFEN GEFUNDEN:\n"
                       f"{', '.join(weapons) if weapons else 'Keine neuen Waffen.'}")
                       
                QMessageBox.information(self, "Session Analyse", msg)
                
        except Exception as e:
            self.show()
            QMessageBox.critical(self, "Kritischer Fehler", f"Fehler im Ablauf:\n{str(e)}")
                
    def run_installer(self):
        selected_row = self.table.currentRow()
        
        if selected_row >= 0:
            item = self.table.item(selected_row, 0)
            map_data = item.data(Qt.UserRole)
            
            if map_data and isinstance(map_data, dict):
                # Download/Install von Doomworld
                title = map_data.get('title', 'Unbekannt')
                self.statusBar().showMessage(f"Lade '{title}' herunter...")
                success, _ = api.download_idgames_gui(map_data, callback=lambda m: self.statusBar().showMessage(m))
                if success:
                    self.refresh_data()
                    QMessageBox.information(self, "Erfolg", f"'{title}' installiert!")
                return # Beenden

        # 2. Wenn nichts ausgewählt ist: Automatisch den INSTALL-Ordner scannen!
        self.statusBar().showMessage("Scanne 'Install'-Ordner nach neuen Karten...")
        
        # Aufruf der neuen Funktion ohne Browser-Fenster!
        count = installer.install_from_folder(callback=lambda m: self.statusBar().showMessage(m))
        
        if count > 0:
            self.refresh_data()
            QMessageBox.information(self, "Auto-Installer", f"{count} Karte(n) erfolgreich aus dem Install-Ordner importiert!")
        else:
            self.statusBar().showMessage("Keine neuen Dateien im 'Install'-Ordner gefunden.")

    def play_random(self):
        """Wird aufgerufen, wenn man auf 'ZUFALL' klickt."""
        if not self.all_maps_data: return
        random_map = random.choice(self.all_maps_data)
        
        # In der Tabelle auswählen und starten
        items = self.table.findItems(random_map['ID'], Qt.MatchExactly)
        if items:
            self.table.selectRow(items[0].row())
        
        self.run_game(random_map['ID'])

    def check_updates(self):
        """Prüft im Hintergrund auf Launcher-Updates."""
        update_info = updater.check_launcher_update()
        if update_info.get("update_available"):
            reply = QMessageBox.question(self, "Update Verfügbar", 
                                        f"Version {update_info['remote_version']} ist verfügbar.\nMöchtest du jetzt updaten?",
                                        QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                if updater.apply_launcher_update(update_info['remote_version'], update_info['remote_code']):
                    QMessageBox.information(self, "Update", "Update erfolgreich! Der Launcher wird nun beendet. Bitte starte ihn neu.")
                    sys.exit(0)

    # --- MENÜS & DIALOGE ---

    def show_context_menu(self, pos):
        """Erstellt das Rechtsklick-Menü"""
        item = self.table.itemAt(pos)
        if not item: return

        # Die ID der Karte aus der Zelle holen
        mid = item.data(Qt.UserRole)
        if not mid: return

        menu = QMenu(self.table)

        # 1. Aktionen definieren
        act_clear = menu.addAction("✔ Map Clear")
        act_mod   = menu.addAction("🅼 Skip Mods")
        act_fav   = menu.addAction("⭐ Favorit") 
        
        menu.addSeparator()
        act_args  = menu.addAction("🛠 Parameter bearbeiten")
        act_del   = menu.addAction("🗑 Map löschen")

        # 2. Menü anzeigen
        action = menu.exec(self.table.mapToGlobal(pos))

        # 3. Auswertung der Klicks
        if action == act_clear:
            db.toggle_map_clear(mid)
            self.refresh_data()
            
        elif action == act_mod:
            db.toggle_mod_skip(mid)
            self.refresh_data()

        elif action == act_fav:
            db.toggle_favorite(mid)
            self.statusBar().showMessage(f"Favoriten-Status für {mid} geändert.")
            self.refresh_data()
            
        elif action == act_args:
            if hasattr(self, 'edit_map_parameters'):
                self.edit_map_parameters(mid)
                
        elif action == act_del:
            self.delete_map(mid)

    def delete_map(self, map_id):
        reply = QMessageBox.question(self, "Löschen", f"Möchtest du Map {map_id} wirklich samt Dateien löschen?", 
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            if db.uninstall_map(map_id):
                QMessageBox.information(self, "Gelöscht", "Map erfolgreich entfernt.")
                self.refresh_data()
            else:
                QMessageBox.warning(self, "Fehler", "Map konnte nicht gelöscht werden (Basis-Spiel?).")

    def open_api(self):
        dlg = ApiBrowserDialog(self)
        dlg.main_refresh_signal.connect(self.refresh_data)
        dlg.exec()

    def open_eng(self):
        """Öffnet den Engine-Manager und aktualisiert danach die GUI."""
        dialog = EngineManagerDialog(self)
        dialog.exec() 
        
        cfg.CURRENT_ENGINE = cfg.get_current_engine() 
        
        self.refresh_data()

    def edit_map_parameters(self, map_id):
        """Öffnet ein Fenster, um die Custom-Parameter (ARGS) einer Map zu bearbeiten."""
        
        # 1. Aktuelle Daten direkt aus der Datenbank holen
        map_data = db.get_map_by_id(map_id)
        if not map_data:
            QMessageBox.warning(self, "Fehler", "Konnte die Kartendaten nicht laden.")
            return

        map_name = map_data.get('Name', 'Unbekannt')
        current_args = str(map_data.get('ARGS', '0')).strip()
        
        # Wenn "0" in der Datenbank steht, machen wir das Eingabefeld für den Nutzer leer
        if current_args == "0":
            current_args = ""

        # 2. Eingabefenster (Prompt) anzeigen
        new_args, ok = QInputDialog.getText(
            self, 
            "Parameter bearbeiten", 
            f"Zusätzliche Engine-Parameter für '{map_name}' eingeben:\n(Beispiel: -fast -nomonsters)\n\nLeer lassen, um Parameter zu entfernen.",
            text=current_args
        )

        if ok:
            final_args = new_args.strip() if new_args.strip() else "0"
            
            if db.update_map_args(map_id, final_args):
                print(f"✅ Parameter für {map_id} gespeichert: {final_args}")
            else:
                QMessageBox.warning(self, "Fehler", "Die Parameter konnten nicht gespeichert werden.")

# ============================================================================
# START
# ============================================================================
if __name__ == "__main__":
    # 1. Geräuschloses Setup ausführen (Ordner & CSV erstellen, falls sie fehlen)
    init.run_initial_setup()

    # 2. GUI starten
    app = QApplication(sys.argv)
    
    # Dunkles Theme aktivieren (sieht für Doom passender aus)
    app.setStyle("Fusion")
    palette = app.palette()
    palette.setColor(palette.ColorRole.Window, QColor(53, 53, 53))
    palette.setColor(palette.ColorRole.WindowText, Qt.GlobalColor.white)
    palette.setColor(palette.ColorRole.Base, QColor(25, 25, 25))
    palette.setColor(palette.ColorRole.AlternateBase, QColor(53, 53, 53))
    palette.setColor(palette.ColorRole.ToolTipBase, Qt.GlobalColor.black)
    palette.setColor(palette.ColorRole.ToolTipText, Qt.GlobalColor.white)
    palette.setColor(palette.ColorRole.Text, Qt.GlobalColor.white)
    palette.setColor(palette.ColorRole.Button, QColor(53, 53, 53))
    palette.setColor(palette.ColorRole.ButtonText, Qt.GlobalColor.white)
    palette.setColor(palette.ColorRole.BrightText, Qt.GlobalColor.red)
    palette.setColor(palette.ColorRole.Link, QColor(42, 130, 218))
    palette.setColor(palette.ColorRole.Highlight, QColor(42, 130, 218))
    palette.setColor(palette.ColorRole.HighlightedText, Qt.GlobalColor.black)
    app.setPalette(palette)

    # 3. Fenster laden
    window = DoomManagerGUI()
    window.show()
    sys.exit(app.exec())