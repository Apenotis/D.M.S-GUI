import sys
import os
import ctypes
import csv
import json
import random
import logging
import traceback
import configparser
from datetime import datetime, timedelta

# Qt widgets in use
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTableWidget, QTableWidgetItem, 
    QVBoxLayout, QHBoxLayout, QPushButton, QWidget, QHeaderView, 
    QLabel, QMenu, QMessageBox, QDialog, QLineEdit, QCheckBox, 
    QGroupBox, QSplitter, QAbstractItemView, QScrollArea, QFrame,
    QComboBox, QFileDialog, QSizePolicy, QTextEdit,
    QInputDialog, QStyledItemDelegate, QStyle
)
from PySide6.QtCore import Qt, Signal, QRect, QSize, QTimer, QPoint, QUrl
from PySide6.QtGui import QAction, QIcon, QColor, QFont, QPainter, QBrush, QFontMetrics, QLinearGradient, QPolygon, QDesktopServices

# ============================================================================
# Core-Module
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
from dms_core.setup_wizard import SetupWizard, should_run_wizard

# Error logging
logging.basicConfig(filename=os.path.join(cfg.BASE_DIR, 'dms_error.log'), level=logging.ERROR, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

# ============================================================================
# Global crash handler
# ============================================================================
def global_exception_handler(exc_type, exc_value, exc_traceback):
    """
    Catch all unhandled errors across the entire program,
    store them in the log, and show a warning in the GUI.
    """
    # Build traceback text.
    tb_lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
    tb_text = "".join(tb_lines)

    # Log the error.
    logging.error(f"UNHANDLED CRASH:\n{tb_text}")
    print("[CRASH] A fatal error occurred. See dms_error.log")

    # Mark startup failures so rollback can be offered.
    updater.mark_start_failure(tb_text)

    # Show the error in the GUI.
    app = QApplication.instance()
    if app:
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowTitle("Critical System Error")
        msg.setText("An unexpected error occurred.\nThe program has to close.")
        msg.setInformativeText("A report was saved to 'dms_error.log'.")
        msg.setDetailedText(tb_text)
        msg.exec()

        backups = updater.get_update_backups()
        if backups:
            rb = QMessageBox.question(
                None,
                "Offer Rollback",
                "At least one update backup was found.\nDo you want to restore the latest backup now?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if rb == QMessageBox.Yes:
                if updater.restore_latest_update_backup():
                    QMessageBox.information(None, "Rollback", "Backup restored. Please restart the launcher.")
                else:
                    QMessageBox.warning(None, "Rollback", "Backup could not be restored.")

    # Exit the process.
    sys.exit(1)

# Enable the global handler.
sys.excepthook = global_exception_handler

# ============================================================================
# Delegate for map display
# ============================================================================
class MapItemDelegate(QStyledItemDelegate):
    """Render flat cards with a colored accent bar and status badges."""

    # Accent colors by status/IWAD
    ACCENT = {
        "favorite": QColor("#FFD700"),
        "cleared":  QColor("#2ecc71"),
        "hexen":    QColor("#9b59b6"),
        "heretic":  QColor("#f1c40f"),
        "doom":     QColor("#c0392b"),
        "none":     QColor("#3a3a3a"),
    }

    # Badge definition: key -> (background, text, text color)
    BADGES = [
        ("n", QColor("#3498db"), "NEW", QColor("#fff")),
        ("f", QColor("#FFD700"), "★", QColor("#111")),
        ("c", QColor("#2ecc71"), "✓", QColor("#111")),
        ("m", QColor("#e67e22"), "M", QColor("#fff")),
    ]

    def paint(self, painter: QPainter, option, index):
        flags = index.data(Qt.UserRole + 1)
        map_id = str(index.data(Qt.UserRole) or "").strip().upper()
        table = self.parent()
        is_enabled = bool(index.flags() & Qt.ItemFlag.ItemIsEnabled)
        is_selected = bool(option.state & QStyle.State_Selected)
        is_hovered = bool(option.state & QStyle.State_MouseOver)
        is_pressed = bool(option.state & QStyle.State_Sunken)

        painter.save()
        rect = option.rect

        # Render disabled cells as background only.
        if not is_enabled or flags is None or not map_id:
            painter.fillRect(rect, QColor("#1e1e1e"))
            painter.restore()
            return

        # Background color, slightly brighter on hover.
        if is_hovered:
            bg = QColor("#2a2a2a")
        else:
            bg = QColor("#222222")

        painter.fillRect(rect, bg)

        # Bottom separator.
        painter.setPen(QColor("#1a1a1a"))
        painter.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())

        # Left accent bar.
        iwad = flags.get("iwad", "")
        if flags.get("f") == "1":
            accent = self.ACCENT["favorite"]
        elif flags.get("c") == "1":
            accent = self.ACCENT["cleared"]
        elif "hexen" in iwad:
            accent = self.ACCENT["hexen"]
        elif "heretic" in iwad:
            accent = self.ACCENT["heretic"]
        else:
            accent = self.ACCENT["doom"]

        bar = QRect(rect.left() + 6, rect.top() + 5, 3, rect.height() - 10)

        # Hover glow on the accent bar.
        if is_hovered:
            glow = QRect(bar.left() - 3, bar.top() - 2, bar.width() + 8, bar.height() + 4)
            glow_color = QColor(accent)
            glow_color.setAlpha(80)
            painter.fillRect(glow, glow_color)

        bar_color = QColor(accent)
        if is_hovered:
            bar_color = bar_color.lighter(145)
        painter.fillRect(bar, bar_color)

        is_animating_this_item = bool(
            table
            and map_id
            and map_id == str(getattr(table, "click_fill_map_id", "") or "")
            and (
                bool(getattr(table, "click_fill_armed", False))
                or float(getattr(table, "click_fill_progress", 0.0) or 0.0) > 0.0
            )
        )

        # Keep the final color only after the click animation finishes.
        if is_selected and not is_animating_this_item:
            hold_rect = rect.adjusted(1, 1, -1, -1)
            hold_base = QColor(accent)
            hold_base.setAlpha(186)
            painter.fillRect(hold_rect, hold_base)

        # Click animation from left to right.
        if table and map_id and map_id == str(getattr(table, "click_fill_map_id", "") or ""):
            progress = float(getattr(table, "click_fill_progress", 0.0) or 0.0)
            if progress > 0.0:
                p = min(1.0, max(0.0, progress))
                fill_rect = rect.adjusted(1, 1, -1, -1)
                fill_w = int(fill_rect.width() * p)
                if fill_w > 0:
                    left = fill_rect.left()
                    top = fill_rect.top()
                    bottom = fill_rect.bottom()
                    right_limit = fill_rect.right()

                    # Leading edge as a seamless polygon.
                    slant = max(6, fill_rect.height() - 1)

                    # Internal travel path including the slanted edge to the right border.
                    travel = fill_rect.width() + slant
                    front_pos = left + int(travel * p)

                    front_top = min(right_limit, front_pos)
                    front_bottom = max(left, min(right_limit, front_pos - slant))

                    slider_poly = QPolygon([
                        QPoint(left, top),
                        QPoint(front_top, top),
                        QPoint(front_bottom, bottom),
                        QPoint(left, bottom),
                    ])

                    slider_color = QColor(accent)
                    slider_color.setAlpha(186)
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(slider_color)
                    painter.drawPolygon(slider_poly)

        # Compute badge rectangles.
        badge_font = QFont("Segoe UI", 7, QFont.Bold)
        painter.setFont(badge_font)
        badge_h = 15
        badge_margin = 4
        badge_x = rect.right() - 6

        active_badges = [(bg_c, txt, fg_c) for key, bg_c, txt, fg_c in self.BADGES if flags.get(key) == "1"]

        badge_rects = []
        for bg_c, txt, fg_c in reversed(active_badges):
            fm = painter.fontMetrics()
            badge_w = fm.horizontalAdvance(txt) + 10
            badge_x -= badge_w
            badge_rects.append((QRect(badge_x, rect.center().y() - badge_h // 2, badge_w, badge_h), bg_c, txt, fg_c))
            badge_x -= badge_margin

        # Reserve text space to the left of the badges.
        text_right = rect.right() - 6 if not badge_rects else min(r.left() for r, *_ in badge_rects) - 6
        text_rect = QRect(rect.left() + 16, rect.top(), text_right - rect.left() - 16, rect.height())

        name_font = QFont("Segoe UI", 10)
        name_font.setBold(flags.get("f") == "1")
        painter.setFont(name_font)

        if flags.get("f") == "1":
            painter.setPen(QColor("#FFD700"))
        elif is_selected:
            painter.setPen(QColor("#ffffff"))
        else:
            painter.setPen(QColor("#dddddd"))

        name = index.data(Qt.DisplayRole) or ""
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, name)

        # Draw badges.
        for b_rect, bg_c, txt, fg_c in badge_rects:
            painter.setPen(Qt.NoPen)
            painter.setBrush(bg_c)
            painter.drawRoundedRect(b_rect, 3, 3)
            painter.setPen(fg_c)
            painter.setFont(badge_font)
            painter.drawText(b_rect, Qt.AlignCenter, txt)

        painter.restore()

    def sizeHint(self, option, index):
        return QSize(200, 40)


# ============================================================================
# Dialogs
# ============================================================================

class EngineManagerDialog(QDialog):
    """Dialog for managing and downloading source ports."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Engine Manager")
        self.resize(500, 400)
        self.layout = QVBoxLayout(self)
        
        self.info_label = QLabel("Manage your engines here:")
        self.layout.addWidget(self.info_label)

        self.table = QTableWidget(0, 2)  # Name and status
        self.table.setHorizontalHeaderLabels(["Engine", "Status"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.layout.addWidget(self.table)
        self.table.setViewportMargins(0, 3, 0, 0)

        btn_layout = QHBoxLayout()
        self.btn_download = QPushButton("Install / Update")
        self.btn_set_active = QPushButton("Set Active")
        btn_layout.addWidget(self.btn_download)
        btn_layout.addWidget(self.btn_set_active)
        self.layout.addLayout(btn_layout)

        self.btn_download.clicked.connect(self.download_selected)
        self.btn_set_active.clicked.connect(self.set_active)

        self.load_engines()

    def get_engine_status(self, engine_name):
        """Check whether the EXE exists in the Engines directory."""
        path = engines.get_engine_path(engine_name)
        return "READY" if os.path.exists(path) else "-"

    def load_engines(self):
        """Scan all supported engines and show their status."""
        self.table.setRowCount(0)
        
        # Read the active engine from configuration.
        import configparser
        config = configparser.ConfigParser()
        config.read(cfg.CONFIG_FILE, encoding="utf-8-sig")
        current_cfg = config.get("SETTINGS", "current_engine", fallback="")

        for row, eng in enumerate(cfg.SUPPORTED_ENGINES):
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(eng))
            
            status = self.get_engine_status(eng)
            status_item = QTableWidgetItem(status)
            
            # Mark the active engine.
            if current_cfg and eng.lower() == current_cfg.lower():
                status_item.setText(f"ACTIVE ({status})")
                color = QColor(46, 204, 113) if status == "READY" else QColor(231, 76, 60)
                status_item.setBackground(color)
            
            self.table.setItem(row, 1, status_item)

    def set_active(self):
        """Set the selected engine as the active launch engine."""
        row = self.table.currentRow()
        if row < 0: return
        eng_name = self.table.item(row, 0).text()
        
        # Load configuration.
        config = configparser.ConfigParser()
        config.read(cfg.CONFIG_FILE, encoding="utf-8-sig")
        
        # Ensure the section exists.
        if not config.has_section("SETTINGS"):
            config.add_section("SETTINGS")
            
        # Set the active engine.
        config.set("SETTINGS", "current_engine", eng_name)
        
        # Save configuration.
        with open(cfg.CONFIG_FILE, "w", encoding="utf-8-sig") as f:
            config.write(f)
            
        # Update the runtime value.
        cfg.CURRENT_ENGINE = eng_name
        
        # Refresh the UI.
        self.load_engines()
        if self.parent():
            self.parent().refresh_data()
            
        QMessageBox.information(self, "Success", f"{eng_name} is now active.")

    def download_selected(self):
        """Use engine_manager to download the selected engine."""
        row = self.table.currentRow()
        if row < 0: return
        eng_name = self.table.item(row, 0).text()
        
        self.info_label.setText(f"Downloading {eng_name}...")
        QApplication.processEvents()
        
        # Start engine installation.
        success = engines.install_engine(eng_name, callback=lambda m: self.info_label.setText(m))
        if success:
            QMessageBox.information(self, "Success", f"{eng_name} was installed.")
            self.load_engines()
        else:
            QMessageBox.critical(self, "Error", "Download failed.")


class ApiBrowserDialog(QDialog):
    main_refresh_signal = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Doomworld (idgames) Browser")
        self.resize(950, 700)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # Search
        search_layout = QHBoxLayout()
        search_layout.setContentsMargins(5, 5, 5, 5)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter a search term...")
        self.btn_search = QPushButton("Search")
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.btn_search)
        self.layout.addLayout(search_layout)

        # Shortcut categories
        shortcut_layout = QHBoxLayout()
        shortcut_layout.setContentsMargins(5, 3, 5, 3)
        shortcut_layout.setSpacing(5)
        
        # Category names must match the API categories.
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
        
        self.layout.addLayout(shortcut_layout)

        # Results table
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Title", "Size", "Rating", "Status"])
        
        # Header styling
        self.table.horizontalHeader().setFixedHeight(38)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, 4):
            self.table.horizontalHeader().setSectionResizeMode(i, QHeaderView.Fixed)
            self.table.setColumnWidth(i, 110)
        self.table.horizontalHeader().setStyleSheet("""
            QHeaderView::section {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                            stop:0 #3a3a3a, stop:1 #2c3e50);
                color: #ecf0f1;
                padding: 8px;
                border: 1px solid #1a1a1a;
                font-weight: bold;
            }
        """)
            
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setContentsMargins(0, 0, 0, 0)
        self.layout.addWidget(self.table)

        # Download and status
        self.btn_download = QPushButton("Download Selected Map")
        self.btn_download.setMinimumHeight(45)
        self.btn_download.setEnabled(False)
        self.btn_download.setStyleSheet("background-color: #2980b9; color: white; font-weight: bold;")
        self.layout.addWidget(self.btn_download)

        self.status_bottom = QLabel("Ready.")
        self.status_bottom.setContentsMargins(5, 5, 5, 5)
        self.layout.addWidget(self.status_bottom)

        # Signal connections
        self.btn_search.clicked.connect(self.perform_search)
        self.search_input.returnPressed.connect(self.perform_search)
        self.table.itemSelectionChanged.connect(lambda: self.btn_download.setEnabled(True))
        self.btn_download.clicked.connect(self.download_map)
        
        self.current_results = []

    def load_top(self, category):
        self.status_bottom.setText(f"Loading top entries for {category}...")
        self.table.setRowCount(0)
        QApplication.processEvents()
        
        try:
            # Load API data.
            self.current_results = api.get_top_wads(category, callback=lambda msg: self.status_bottom.setText(msg))
            self.populate_table()
        except Exception as e:
            # Show the specific error in the status line.
            error_type = type(e).__name__
            self.status_bottom.setText(f"API error ({error_type}): {str(e)[:50]}...")
            print(f"[GUI DEBUG] Detailed error: {traceback.format_exc()}")

    def perform_search(self):
        query = self.search_input.text().strip()
        if not query: return
        self.status_bottom.setText(f"Searching for '{query}'...")
        QApplication.processEvents()
        self.current_results = api.search_idgames(query)
        self.populate_table()

    def populate_table(self):
        
        # Block signals while rebuilding the table.
        self.table.blockSignals(True)
        
        try:
            self.table.setRowCount(0)
            self.status_bottom.setText(f"Processing {len(self.current_results)} results...")
            
            for row, res in enumerate(self.current_results):
                self.table.insertRow(row)
                
                # Read values from the API result.
                title = res.get("title") or res.get("filename", "Unknown")
                size_mb = f"{int(res.get('size', 0)) / (1024*1024):.1f} MB"
                rating = f"{float(res.get('rating', 0) or 0):.1f} ★"
                is_installed = res.get("is_installed", False)
                
                # Create table items.
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

                # Highlight installed entries.
                if is_installed:
                    green = QColor(46, 204, 113)
                    bold_font = QFont("Arial", 9, QFont.Bold)
                    
                    item_title.setForeground(green)
                    item_status.setForeground(green)
                    item_status.setFont(bold_font)

                # Set items.
                self.table.setItem(row, 0, item_title)
                self.table.setItem(row, 1, item_size)
                self.table.setItem(row, 2, item_rating)
                self.table.setItem(row, 3, item_status)

        finally:
            # Re-enable signals.
            self.table.blockSignals(False)
            self.status_bottom.setText(f"{len(self.current_results)} results found.")

    def download_map(self):
        row = self.table.currentRow()
        if row < 0: return
        file_data = self.current_results[row]
        
        # Show a progress dialog for the download.
        wait_dlg = QDialog(self)
        wait_dlg.setWindowTitle("Installing...")
        wait_dlg.setModal(True)
        wait_dlg.setFixedSize(380, 110)
        wait_layout = QVBoxLayout(wait_dlg)
        wait_label = QLabel(f"\u2b07  Downloading and installing:\n\n  {file_data.get('title', '')}\n\nPlease wait...")
        wait_label.setWordWrap(True)
        wait_layout.addWidget(wait_label)
        wait_dlg.show()
        QApplication.processEvents()
        
        self.btn_download.setEnabled(False)
        
        def _update(t):
            self.status_bottom.setText(t)
            wait_label.setText(f"\u2b07  {t}")
            QApplication.processEvents()
        
        success, msg = api.download_idgames_gui(file_data, callback=_update)
        wait_dlg.close()
        
        if success:
            QMessageBox.information(self, "Success", f"Download complete.\nID: {msg}")
            parent = self.parent()
            if parent and hasattr(parent, "set_pending_focus_map"):
                parent.set_pending_focus_map(msg)
            self.main_refresh_signal.emit()
            self.populate_table()
        else:
            QMessageBox.critical(self, "Error", f"Download failed:\n{msg}")
        
        self.btn_download.setEnabled(True)


class DatabaseViewerDialog(QDialog):
    """Show a live view of the SQLite database and allow exports."""

    DISPLAY_HEADER = [
        "ID", "Name", "IWAD", "Path", "Category",
        "MOD", "ARGS", "Playtime", "LastPlayed", "RemoteID",
        "Favorite", "Cleared", "NoMods"
    ]

    FIELD_MAP = {
        "Category": "Kategorie",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("DB Viewer (maps.db)")
        self.resize(1050, 650)

        self.all_rows = []

        layout = QVBoxLayout(self)

        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Category:"))
        self.cmb_category = QComboBox()
        self.cmb_category.addItem("ALL")
        filter_layout.addWidget(self.cmb_category)

        filter_layout.addWidget(QLabel("IWAD:"))
        self.cmb_iwad = QComboBox()
        self.cmb_iwad.addItem("ALL")
        filter_layout.addWidget(self.cmb_iwad)

        filter_layout.addWidget(QLabel("Search:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("ID or name...")
        filter_layout.addWidget(self.search_input, 1)

        self.btn_reload = QPushButton("Reload")
        filter_layout.addWidget(self.btn_reload)
        layout.addLayout(filter_layout)

        self.table = QTableWidget(0, len(self.DISPLAY_HEADER))
        self.table.setHorizontalHeaderLabels(self.DISPLAY_HEADER)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)

        export_layout = QHBoxLayout()
        self.lbl_info = QLabel("0 entries")
        export_layout.addWidget(self.lbl_info)
        export_layout.addStretch()
        self.btn_export_csv = QPushButton("Export CSV")
        self.btn_export_json = QPushButton("Export JSON")
        export_layout.addWidget(self.btn_export_csv)
        export_layout.addWidget(self.btn_export_json)
        layout.addLayout(export_layout)

        self.cmb_category.currentTextChanged.connect(self.apply_filters)
        self.cmb_iwad.currentTextChanged.connect(self.apply_filters)
        self.search_input.textChanged.connect(self.apply_filters)
        self.btn_reload.clicked.connect(self.load_from_db)
        self.btn_export_csv.clicked.connect(self.export_csv)
        self.btn_export_json.clicked.connect(self.export_json)

        self.load_from_db()

    def load_from_db(self):
        self.all_rows = db.get_all_maps()

        categories = sorted({str(r.get("Kategorie", "")).upper() for r in self.all_rows if r.get("Kategorie")})
        iwads = sorted({str(r.get("IWAD", "")).lower() for r in self.all_rows if r.get("IWAD")})

        self.cmb_category.blockSignals(True)
        self.cmb_iwad.blockSignals(True)

        self.cmb_category.clear()
        self.cmb_category.addItem("ALL")
        for c in categories:
            self.cmb_category.addItem(c)

        self.cmb_iwad.clear()
        self.cmb_iwad.addItem("ALL")
        for iwad in iwads:
            self.cmb_iwad.addItem(iwad)

        self.cmb_category.blockSignals(False)
        self.cmb_iwad.blockSignals(False)

        self.apply_filters()

    def _get_filtered_rows(self):
        selected_cat = self.cmb_category.currentText().strip().upper()
        selected_iwad = self.cmb_iwad.currentText().strip().lower()
        needle = self.search_input.text().strip().lower()

        filtered = []
        for row in self.all_rows:
            cat = str(row.get("Kategorie", "")).upper()
            iwad = str(row.get("IWAD", "")).lower()
            map_id = str(row.get("ID", "")).lower()
            name = str(row.get("Name", "")).lower()

            if selected_cat != "ALL" and cat != selected_cat:
                continue
            if selected_iwad != "all" and iwad != selected_iwad:
                continue
            if needle and needle not in map_id and needle not in name:
                continue
            filtered.append(row)
        return filtered

    def apply_filters(self):
        filtered = self._get_filtered_rows()
        self.table.setRowCount(len(filtered))

        for row_index, row_data in enumerate(filtered):
            for col_index, col_name in enumerate(self.DISPLAY_HEADER):
                source_key = self.FIELD_MAP.get(col_name, col_name)
                value = str(row_data.get(source_key, ""))
                self.table.setItem(row_index, col_index, QTableWidgetItem(value))

        self.lbl_info.setText(f"{len(filtered)} of {len(self.all_rows)} entries")

    def export_csv(self):
        rows = self._get_filtered_rows()
        if not rows:
            QMessageBox.information(self, "Export", "No data available for export.")
            return

        target, _ = QFileDialog.getSaveFileName(self, "Export CSV", os.path.join(cfg.BASE_DIR, "maps_export.csv"), "CSV (*.csv)")
        if not target:
            return

        try:
            with open(target, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=db.HEADER, delimiter=";", extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows)
            QMessageBox.information(self, "Export", f"CSV exported successfully:\n{target}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))

    def export_json(self):
        rows = self._get_filtered_rows()
        if not rows:
            QMessageBox.information(self, "Export", "No data available for export.")
            return

        target, _ = QFileDialog.getSaveFileName(self, "Export JSON", os.path.join(cfg.BASE_DIR, "maps_export.json"), "JSON (*.json)")
        if not target:
            return

        try:
            with open(target, "w", encoding="utf-8") as f:
                json.dump(rows, f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, "Export", f"JSON exported successfully:\n{target}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))


class InstallToast(QFrame):
    """Small popup in the lower-right corner with an action to jump to a map."""
    jump_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setStyleSheet(
            "QFrame { background-color: #1f2a33; border: 1px solid #3a4b57; border-radius: 8px; }"
            "QLabel { color: #e5edf3; }"
            "QPushButton { background-color: #2980b9; color: white; border: none; border-radius: 5px; padding: 5px 10px; }"
            "QPushButton:hover { background-color: #3498db; }"
        )

        self.current_map_id = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        self.lbl_title = QLabel("Map installed")
        self.lbl_title.setStyleSheet("font-weight: bold;")
        self.lbl_msg = QLabel("-")
        self.lbl_msg.setWordWrap(True)

        btn_row = QHBoxLayout()
        self.btn_jump = QPushButton("Jump To")
        self.btn_close = QPushButton("X")
        self.btn_close.setFixedWidth(28)
        self.btn_close.setStyleSheet(
            "QPushButton { background-color: #3a4b57; color: #d7e1e8; border: none; border-radius: 5px; padding: 5px; }"
            "QPushButton:hover { background-color: #546a79; }"
        )
        self.btn_jump.clicked.connect(self._on_jump)
        self.btn_close.clicked.connect(self.hide)
        btn_row.addWidget(self.btn_jump)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_close)

        layout.addWidget(self.lbl_title)
        layout.addWidget(self.lbl_msg)
        layout.addLayout(btn_row)

        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide)

    def show_for_map(self, map_id):
        self.current_map_id = str(map_id or "").strip().upper()
        if not self.current_map_id:
            return

        self.lbl_msg.setText(f"Map installed: {self.current_map_id}")
        self.adjustSize()
        self._position_bottom_right()
        self.show()
        self.raise_()
        self.hide_timer.start(9000)

    def _position_bottom_right(self):
        parent = self.parentWidget()
        if not parent:
            return

        global_pos = parent.mapToGlobal(parent.rect().bottomRight())
        x = global_pos.x() - self.width() - 16
        y = global_pos.y() - self.height() - 40
        self.move(max(10, x), max(10, y))

    def _on_jump(self):
        if self.current_map_id:
            self.jump_requested.emit(self.current_map_id)
        self.hide()


# ============================================================================
# Main GUI
# ============================================================================

class DoomManagerGUI(QMainWindow):
    signal_refresh = Signal()
    NEW_WINDOW_HOURS = 72
    CHANGELOG_TAG = "3.1-ui-2026-04"
    CLICK_FILL_SPEED = 7

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Doom Management System (D.M.S.) v{cfg.APP_VERSION}")
        self.resize(1450, 900)
        
        self.all_maps_data = []
        self.pending_focus_map_id = None
        self.sort_mode = cfg.config.get("SETTINGS", "map_sort_mode", fallback="insert")
        self.quick_filter = cfg.config.get("SETTINGS", "map_quick_filter", fallback="ALLE").upper()
        self.recent_installs = self._load_recent_installs()
        self.preview_title_full_text = "No map selected"
        self.preview_path_full_text = "Path: -"
        self.install_toast = None
        self.click_fill_map_id = ""
        self.click_fill_progress = 0.0
        self.click_fill_timer = QTimer(self)
        self.click_fill_timer.setInterval(20)
        self.click_fill_timer.timeout.connect(self._advance_click_fill)
        self.signal_refresh.connect(self.refresh_data)

        self.setup_ui()
        self.install_toast = InstallToast(self)
        self.install_toast.jump_requested.connect(self.jump_to_map)
        self.refresh_data()
        
        # Setup wizard on first start.
        if should_run_wizard():
            wizard = SetupWizard(self)
            wizard.wizard_complete.connect(self.refresh_data)
            wizard.exec()
        
        # Check for updates on startup.
        self.check_updates()
        self.maybe_show_changelog()

        # Optional startup scan for local imports without a permanent watcher.
        if cfg.config.getboolean("SETTINGS", "install_scan_on_startup", fallback=False):
            QTimer.singleShot(800, lambda: self.run_install_scan(show_empty_message=False, auto_mode=True))

    def set_pending_focus_map(self, map_id, show_toast=True):
        """Remember a map ID that should be focused after the next refresh."""
        if map_id:
            clean_id = str(map_id).strip().upper()
            self.pending_focus_map_id = clean_id
            self.mark_maps_as_new([clean_id])
            if show_toast:
                self.show_install_toast(clean_id)

    def show_install_toast(self, map_id):
        """Show a small install popup in the lower-right corner with a jump button."""
        if self.install_toast:
            self.install_toast.show_for_map(map_id)

    def jump_to_map(self, map_id):
        """Jump directly to a map ID in the current table."""
        clean_id = str(map_id or "").strip().upper()
        if not clean_id:
            return

        if not self._focus_map_in_table(clean_id):
            self.pending_focus_map_id = clean_id
            self.refresh_data()

    def maybe_show_changelog(self):
        """Show the changelog once per tagged version after app startup."""
        seen_tag = cfg.config.get("SETTINGS", "last_seen_changelog", fallback="").strip()
        if seen_tag != self.CHANGELOG_TAG:
            self.show_changelog(force=False)
            cfg.update_config_value("SETTINGS", "last_seen_changelog", self.CHANGELOG_TAG)

    def _capture_map_ids(self):
        """Return a normalized set of current map IDs for before/after install checks."""
        return {str(m.get("ID", "")).strip().upper() for m in db.get_all_maps() if m.get("ID")}

    def _mark_new_maps_from_diff(self, before_ids):
        """Mark and focus newly created IDs compared to a previous snapshot."""
        after_ids = self._capture_map_ids()
        new_ids = sorted(after_ids - set(before_ids), key=self._sort_map_id_key)
        if new_ids:
            self.mark_maps_as_new(new_ids)
            self.set_pending_focus_map(new_ids[-1])
        return len(new_ids)

    def _get_backup_keep_count(self):
        """Load backup retention count from config with a safe fallback."""
        raw_value = cfg.config.get("SETTINGS", "backup_keep_count", fallback="10").strip()
        try:
            return max(1, int(raw_value))
        except Exception:
            return 10

    def create_guard_backup(self, label, show_message=False):
        """Create a ZIP backup and prune old snapshots according to retention settings."""
        try:
            backup_path = updater.create_update_backup(label)
            removed = updater.prune_update_backups(self._get_backup_keep_count())
            status_msg = f"Backup created: {os.path.basename(backup_path)}"
            if removed > 0:
                status_msg += f" | Removed old backups: {removed}"
            self.statusBar().showMessage(status_msg, 7000)
            if show_message:
                QMessageBox.information(self, "Backup", status_msg)
            return backup_path
        except Exception as e:
            QMessageBox.warning(self, "Backup", f"Backup could not be created:\n{e}")
            return ""

    def create_manual_backup(self):
        """Create a user-triggered backup snapshot from the top bar."""
        self.create_guard_backup("manual")

    def restore_backup_dialog(self):
        """Allow selecting and restoring one ZIP backup from update_backups/."""
        backups = updater.get_update_backups()
        if not backups:
            QMessageBox.information(self, "Restore Backup", "No backups were found.")
            return

        display_to_path = {}
        options = []
        for path in backups:
            size_kb = max(1, int(os.path.getsize(path) / 1024))
            label = f"{os.path.basename(path)} ({size_kb} KB)"
            display_to_path[label] = path
            options.append(label)

        selected, ok = QInputDialog.getItem(
            self,
            "Restore Backup",
            "Select a backup to restore:",
            options,
            0,
            False,
        )
        if not ok:
            return

        chosen_path = display_to_path.get(selected)
        if not chosen_path:
            return

        # Keep a fresh snapshot before overwrite so rollback is always possible.
        self.create_guard_backup("prerestore")

        confirm = QMessageBox.question(
            self,
            "Restore Backup",
            "Restore this backup now? The current state will be overwritten.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        if updater.restore_update_backup(chosen_path):
            QMessageBox.information(self, "Restore Backup", "Backup restored. Restart the launcher to ensure a clean state.")
        else:
            QMessageBox.warning(self, "Restore Backup", "Backup restore failed.")

    def update_install_scan_button_text(self):
        """Reflect startup scan mode in the top bar button text."""
        enabled = cfg.config.getboolean("SETTINGS", "install_scan_on_startup", fallback=False)
        self.btn_install_scan_toggle.setText("🧲 Startup Scan: ON" if enabled else "🧲 Startup Scan: OFF")

    def toggle_install_scan_on_startup(self):
        """Enable or disable Install folder scanning on startup."""
        current = cfg.config.getboolean("SETTINGS", "install_scan_on_startup", fallback=False)
        cfg.update_config_value("SETTINGS", "install_scan_on_startup", "False" if current else "True")
        self.update_install_scan_button_text()

    def _build_changelog_html(self):
        """Return the compact What's New text."""
        return (
            "<b>Mini Changelog</b><br><br>"
            "<b>UI & Navigation</b><br>"
            "- Live search with quick filter chips<br>"
            "- Sort menu with persistence<br>"
            "- New maps receive a NEW badge<br><br>"
            "<b>Install Flow</b><br>"
            "- Bottom-right popup: 'Map installed'<br>"
            "- 'Jump To' button focuses the installed map<br><br>"
            "<b>Convenience</b><br>"
            "- Random map uses visible/filtered maps<br>"
            "- Preview panel with map metadata<br>"
            "- Expanded dashboard (Clear %, FAV, NEW, VIEW)"
        )

    def show_changelog(self, force=False):
        """Show the mini changelog dialog."""
        msg = QMessageBox(self)
        msg.setWindowTitle("What's New")
        msg.setIcon(QMessageBox.Information)
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setText(self._build_changelog_html())
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        if not force:
            msg.setInformativeText("This notice is shown once per version update.")
        msg.exec()

    def _load_recent_installs(self):
        """Read NEW markers from configuration and remove stale entries."""
        raw = cfg.config.get("SETTINGS", "recent_installs", fallback="").strip()
        installs = {}

        if raw:
            for chunk in raw.split(";"):
                if "|" not in chunk:
                    continue
                map_id, iso_time = chunk.split("|", 1)
                map_id = str(map_id).strip().upper()
                iso_time = str(iso_time).strip()
                if map_id and iso_time:
                    installs[map_id] = iso_time

        self.recent_installs = installs
        self._prune_recent_installs()
        return self.recent_installs

    def _save_recent_installs(self):
        """Persist NEW markers compactly as SETTINGS.recent_installs."""
        if not self.recent_installs:
            cfg.update_config_value("SETTINGS", "recent_installs", "")
            return

        payload = ";".join(f"{mid}|{iso}" for mid, iso in sorted(self.recent_installs.items()))
        cfg.update_config_value("SETTINGS", "recent_installs", payload)

    def _prune_recent_installs(self):
        """Remove NEW markers older than the configured time window."""
        cutoff = datetime.now() - timedelta(hours=self.NEW_WINDOW_HOURS)
        keep = {}

        for mid, iso_time in self.recent_installs.items():
            try:
                dt = datetime.fromisoformat(iso_time)
                if dt >= cutoff:
                    keep[mid] = iso_time
            except Exception:
                continue

        self.recent_installs = keep

    def mark_maps_as_new(self, map_ids):
        """Mark one or more maps as NEW and persist the result."""
        now_iso = datetime.now().isoformat(timespec="seconds")
        changed = False

        for map_id in map_ids:
            mid = str(map_id or "").strip().upper()
            if not mid:
                continue
            self.recent_installs[mid] = now_iso
            changed = True

        if changed:
            self._prune_recent_installs()
            self._save_recent_installs()

    def _is_recent_install(self, map_id):
        """Check whether a map is currently marked as NEW."""
        mid = str(map_id or "").strip().upper()
        if not mid:
            return False

        iso_time = self.recent_installs.get(mid)
        if not iso_time:
            return False

        try:
            dt = datetime.fromisoformat(iso_time)
        except Exception:
            return False

        return dt >= (datetime.now() - timedelta(hours=self.NEW_WINDOW_HOURS))

    def _sort_map_id_key(self, map_id):
        """Sort key for IDs such as DOOM123 or HEXEN7."""
        mid = str(map_id or "").strip().upper()
        prefix = "".join(ch for ch in mid if ch.isalpha())
        suffix = "".join(ch for ch in mid if ch.isdigit())
        number = int(suffix) if suffix.isdigit() else -1
        return (prefix, number, mid)

    def _focus_map_in_table(self, map_id):
        """Find a map in any column, select it, and scroll it into view."""
        target = str(map_id or "").strip().upper()
        if not target:
            return False

        for row in range(self.table.rowCount()):
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                if not item:
                    continue

                item_id = str(item.data(Qt.UserRole) or "").strip().upper()
                if item_id == target:
                    self.table.setCurrentItem(item)
                    self.table.scrollToItem(item, QAbstractItemView.ScrollHint.PositionAtCenter)
                    self.table.setFocus()
                    return True
        return False

    def setup_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        # Top bar
        top_layout = QHBoxLayout()
        
        self.btn_api = QPushButton("🌐 Doomworld")
        self.btn_eng = QPushButton("⚙️ Engine Manager")
        self.btn_backup_create = QPushButton("💾 Create Backup")
        self.btn_backup_restore = QPushButton("♻ Restore Backup")
        self.btn_install_scan = QPushButton("🔎 Scan Install")
        self.btn_install_scan_toggle = QPushButton("")
        self.btn_install = QPushButton("📥 Install Maps")
        self.btn_manual_add = QPushButton("➕ Custom Map")
        self.btn_db_viewer = QPushButton("🗄 DB Viewer")
        self.btn_changelog = QPushButton("📝 What's New")
        self.btn_tracker_toggle = QPushButton("")

        # Connect buttons
        self.btn_api.clicked.connect(self.open_api)
        self.btn_eng.clicked.connect(self.open_eng)
        self.btn_backup_create.clicked.connect(self.create_manual_backup)
        self.btn_backup_restore.clicked.connect(self.restore_backup_dialog)
        self.btn_install_scan.clicked.connect(lambda: self.run_install_scan(show_empty_message=True, auto_mode=False))
        self.btn_install_scan_toggle.clicked.connect(self.toggle_install_scan_on_startup)
        self.btn_install.clicked.connect(self.run_installer)
        self.btn_manual_add.clicked.connect(self.add_map_manually)
        self.btn_db_viewer.clicked.connect(self.open_db_viewer)
        self.btn_changelog.clicked.connect(lambda: self.show_changelog(force=True))
        self.btn_tracker_toggle.clicked.connect(self.toggle_tracker)

        self.update_tracker_button_text()
        self.update_install_scan_button_text()
        
        top_layout.addStretch()  # Align buttons to the right.
        top_layout.addWidget(self.btn_tracker_toggle)
        top_layout.addWidget(self.btn_install_scan_toggle)
        top_layout.addWidget(self.btn_backup_restore)
        top_layout.addWidget(self.btn_backup_create)
        top_layout.addWidget(self.btn_changelog)
        top_layout.addWidget(self.btn_db_viewer)
        top_layout.addWidget(self.btn_manual_add)
        top_layout.addWidget(self.btn_install_scan)
        top_layout.addWidget(self.btn_install)
        top_layout.addWidget(self.btn_api)
        top_layout.addWidget(self.btn_eng)
        layout.addLayout(top_layout)

        # Main splitter
        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter)

        # Left table
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["", "", "", "", ""])
        self.table.horizontalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectItems) 
        
        # Table styling (the delegate renders cells)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.setMouseTracking(True)
        self.table.viewport().setMouseTracking(True)

        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #1e1e1e;
                border: none;
            }
            QTableWidget::item {
                background-color: transparent;
                border: none;
                padding: 0px;
            }
            QTableWidget::item:selected {
                background-color: transparent;
                border: none;
            }
        """)
        self.table.click_fill_map_id = ""
        self.table.click_fill_progress = 0.0
        self.table.click_fill_armed = False
        self.table.setItemDelegate(MapItemDelegate(self.table))
        # Delegate active

        # Table signals
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        self.table.itemDoubleClicked.connect(self.run_selected_map)
        self.table.itemPressed.connect(self.on_table_item_pressed)
        self.table.itemSelectionChanged.connect(self.update_map_preview)

        header_container = QWidget()
        header_layout = QHBoxLayout(header_container)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(0)

        lbl_doom_header = QLabel("  ▌  Doom Maps")
        lbl_doom_header.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        lbl_doom_header.setStyleSheet(
            "color: #dddddd; font-family: 'Segoe UI', Arial, sans-serif;"
            " font-size: 12px; font-weight: bold; letter-spacing: 1px;"
            " background-color: #1e1e1e;"
            " padding: 8px 12px;"
            " border-bottom: 2px solid #c0392b;"
        )

        lbl_heretic_header = QLabel("  ▌  Heretic / Hexen / Extras")
        lbl_heretic_header.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        lbl_heretic_header.setStyleSheet(
            "color: #dddddd; font-family: 'Segoe UI', Arial, sans-serif;"
            " font-size: 12px; font-weight: bold; letter-spacing: 1px;"
            " background-color: #1e1e1e;"
            " padding: 8px 12px;"
            " border-bottom: 2px solid #f1c40f;"
        )

        header_layout.addWidget(lbl_doom_header, 4)
        header_layout.addWidget(lbl_heretic_header, 1)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        left_layout.addWidget(header_container)

        # Live search for map lists
        self.map_search_input = QLineEdit()
        self.map_search_input.setPlaceholderText("Search maps (name, ID, IWAD)...")
        self.map_search_input.setClearButtonEnabled(True)
        self.map_search_input.setStyleSheet(
            "QLineEdit {"
            " background-color: #232323;"
            " color: #dddddd;"
            " border: 1px solid #444;"
            " border-radius: 4px;"
            " padding: 6px 8px;"
            " margin: 6px;"
            "}"
            "QLineEdit:focus {"
            " border: 1px solid #c0392b;"
            "}"
        )
        self.map_search_input.textChanged.connect(self.refresh_data)
        left_layout.addWidget(self.map_search_input)

        controls_widget = QWidget()
        controls_layout = QVBoxLayout(controls_widget)
        controls_layout.setContentsMargins(6, 0, 6, 6)
        controls_layout.setSpacing(6)

        lbl_sort = QLabel("Sort:")
        lbl_sort.setStyleSheet("color: #bcbcbc; font-weight: bold;")
        self.cmb_sort = QComboBox()
        self.cmb_sort.addItem("Default", "insert")
        self.cmb_sort.addItem("Newest first", "newest")
        self.cmb_sort.addItem("Name A-Z", "name_asc")
        self.cmb_sort.addItem("Favorites first", "fav_first")
        self.cmb_sort.addItem("Last played", "last_played")
        self.cmb_sort.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.cmb_sort.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.cmb_sort.setStyleSheet(
            "QComboBox { background-color: #232323; color: #dddddd; border: 1px solid #444; border-radius: 4px; padding: 4px 8px; }"
            "QComboBox::drop-down { border: none; }"
        )
        sort_idx = self.cmb_sort.findData(self.sort_mode)
        self.cmb_sort.setCurrentIndex(sort_idx if sort_idx >= 0 else 0)
        self.cmb_sort.currentIndexChanged.connect(self.on_sort_mode_changed)

        chips_row = QHBoxLayout()
        chips_row.setSpacing(6)
        self.quick_filter_buttons = {}
        chip_defs = [
            ("ALLE", "All"),
            ("DOOM", "Doom"),
            ("HERETIC", "Heretic"),
            ("HEXEN", "Hexen"),
        ]

        for key, label in chip_defs:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setMinimumHeight(28)
            btn.setStyleSheet(
                "QPushButton { background-color: #2a2a2a; color: #d0d0d0; border: 1px solid #444; border-radius: 12px; padding: 3px 10px; }"
                "QPushButton:hover { border-color: #666; }"
                "QPushButton:checked { background-color: #c0392b; color: #fff; border-color: #e74c3c; }"
            )
            btn.clicked.connect(lambda checked=False, k=key: self.set_quick_filter(k))
            chips_row.addWidget(btn)
            self.quick_filter_buttons[key] = btn

        chips_row.addStretch()
        controls_layout.addLayout(chips_row)

        info_row = QHBoxLayout()
        legend = QLabel(
            "<span style='color:#3498db; font-weight:bold;'>NEW</span> = newly installed   "
            "<span style='color:#FFD700; font-weight:bold;'>★</span> = Favorite   "
            "<span style='color:#2ecc71; font-weight:bold;'>✓</span> = Clear   "
            "<span style='color:#e67e22; font-weight:bold;'>M</span> = Mods locked"
        )
        legend.setStyleSheet("color: #bcbcbc; font-size: 11px; padding-left: 2px;")
        info_row.addWidget(legend)
        info_row.addStretch()
        info_row.addWidget(lbl_sort)
        info_row.addWidget(self.cmb_sort)
        controls_layout.addLayout(info_row)

        left_layout.addWidget(controls_widget)
        self.set_quick_filter(self.quick_filter, persist=False)

        left_layout.addWidget(self.table)

        splitter.addWidget(left_panel)

        # Right panel
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 0, 10, 10)

        # Map preview
        preview_group = QGroupBox("Map Preview")
        preview_group.setStyleSheet("""
            QGroupBox { font-weight: bold; border: 1px solid #555; border-radius: 5px; margin-top: 8px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; color: #aaa; }
        """)
        preview_layout = QVBoxLayout()
        preview_layout.setContentsMargins(8, 8, 8, 6)
        preview_layout.setSpacing(3)

        self.preview_title = QLabel("No map selected")
        self.preview_title.setStyleSheet("color: #ecf0f1; font-size: 13px; font-weight: bold;")
        self.preview_title.setWordWrap(False)
        self.preview_title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.preview_tag = QLabel("-")
        self.preview_tag.setAlignment(Qt.AlignCenter)
        self.preview_tag.setFixedHeight(20)
        self.preview_tag.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.preview_tag.setStyleSheet("background-color: #3a3a3a; color: #dcdcdc; border-radius: 10px; font-size: 11px; padding: 0 8px;")
        self.preview_meta = QLabel("ID: -\nIWAD: -\nCategory: -")
        self.preview_meta.setStyleSheet("color: #b8b8b8;")
        self.preview_meta.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.preview_play = QLabel("Playtime: 0 min\nLast Played: -")
        self.preview_play.setStyleSheet("color: #9aa0a6;")
        self.preview_path = QLabel("Path: -")
        self.preview_path.setStyleSheet("color: #8f8f8f;")
        self.preview_path.setWordWrap(False)
        self.preview_path.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

        preview_layout.addWidget(self.preview_title)
        preview_layout.addWidget(self.preview_tag, 0, Qt.AlignLeft)
        preview_layout.addWidget(self.preview_meta)
        preview_layout.addWidget(self.preview_play)
        preview_layout.addWidget(self.preview_path)
        preview_group.setLayout(preview_layout)
        right_layout.addWidget(preview_group)
        
        # Mod selection with scroll area
        mod_group = QGroupBox("Available Mods")
        # Compact group box styling
        mod_group.setStyleSheet("""
            QGroupBox { font-weight: bold; border: 1px solid #555; border-radius: 5px; margin-top: 8px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; color: #aaa; }
        """)
        
        # Container widget
        mod_container = QWidget()
        self.mod_layout = QVBoxLayout(mod_container)
        self.mod_layout.setAlignment(Qt.AlignTop) 
        self.mod_layout.setSpacing(2)
        self.mod_layout.setContentsMargins(5, 5, 5, 5)
        
        # Scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(mod_container)
        scroll_area.setFrameShape(QScrollArea.NoFrame)
        scroll_area.setStyleSheet("QScrollArea { background: transparent; }")
        
        # Place the scroll area inside the group box
        group_layout = QVBoxLayout()
        # Reduce the top inner margin of the group box.
        group_layout.setContentsMargins(2, 8, 2, 2) 
        group_layout.addWidget(scroll_area)
        mod_group.setLayout(group_layout)
        
        right_layout.addWidget(mod_group)
        
        # Build mod list
        self.populate_mods() 
        
        # Spacer
        right_layout.addSpacing(10)

        # Aktionen
        self.cb_debug = QCheckBox("🛠 Debug Mode (Preview)")
        self.cb_debug.setStyleSheet("color: #e67e22; font-weight: bold;")
        right_layout.addWidget(self.cb_debug)

        self.btn_random = QPushButton("🎲 RANDOM MAP")
        self.btn_random.setMinimumHeight(40)
        self.btn_random.clicked.connect(self.play_random)
        right_layout.addWidget(self.btn_random)

        self.btn_run = QPushButton("▶ START GAME")
        self.btn_run.setMinimumHeight(60)
        self.btn_run.setStyleSheet("""
            QPushButton { background-color: #27ae60; color: white; font-weight: bold; font-size: 14px; border-radius: 4px; }
            QPushButton:hover { background-color: #2ecc71; }
            QPushButton:pressed { background-color: #219653; }
        """)
        self.btn_run.clicked.connect(self.run_selected_map)
        right_layout.addWidget(self.btn_run)

        self.btn_exit = QPushButton("✖ EXIT")
        self.btn_exit.setMinimumHeight(40)
        self.btn_exit.setStyleSheet("""
            QPushButton { background-color: #c0392b; color: white; font-weight: bold; font-size: 12px; border-radius: 4px; }
            QPushButton:hover { background-color: #e74c3c; }
            QPushButton:pressed { background-color: #a93226; }
        """)
        self.btn_exit.clicked.connect(self.close)
        right_layout.addWidget(self.btn_exit)

        splitter.addWidget(right_panel)
        
        # Start the right panel at its minimum width.
        min_right_width = right_panel.minimumSizeHint().width()
        left_width = max(200, self.width() - min_right_width)
        splitter.setSizes([left_width, min_right_width])

        self.statusBar().showMessage("Ready.")

        # Dashboard panel
        self.stats_panel = QFrame()
        self.stats_panel.setObjectName("Dashboard")
        self.stats_panel.setFixedHeight(35)
        self.stats_panel.setStyleSheet("background-color: #252525; border-top: 1px solid #444;")
        
        stats_layout = QHBoxLayout(self.stats_panel)
        stats_layout.setContentsMargins(15, 0, 15, 0)

        # Dashboard labels
        self.stat_count = QLabel("📂 MAPS: -")
        self.stat_cleared = QLabel("✅ CLEAR: -")
        self.stat_cleared.setStyleSheet("color: #2ecc71;") 
        self.stat_favorites = QLabel("⭐ FAV: -")
        self.stat_favorites.setStyleSheet("color: #f1c40f;")
        self.stat_new = QLabel("🆕 NEW: -")
        self.stat_new.setStyleSheet("color: #3498db;")
        self.stat_playtime = QLabel("🕒 TIME: -")
        self.stat_engine = QLabel("⚙️ ENGINE: -")
        self.stat_view = QLabel("🔎 VIEW: -")
        self.stat_view.setStyleSheet("color: #9aa0a6;")

        def get_sep():
            sep = QLabel("|")
            sep.setStyleSheet("color: #444;")
            return sep

        # Insert dashboard into the layout
        stats_layout.addWidget(self.stat_count)
        stats_layout.addWidget(get_sep())
        stats_layout.addWidget(self.stat_cleared)
        stats_layout.addWidget(get_sep())
        stats_layout.addWidget(self.stat_favorites)
        stats_layout.addWidget(get_sep())
        stats_layout.addWidget(self.stat_new)
        stats_layout.addWidget(get_sep())
        stats_layout.addWidget(self.stat_playtime)
        stats_layout.addWidget(get_sep())
        stats_layout.addWidget(self.stat_engine)
        stats_layout.addWidget(get_sep())
        stats_layout.addWidget(self.stat_view)
        stats_layout.addStretch()

        layout.addWidget(self.stats_panel)

        self.update_stats()

    def resizeEvent(self, event):
        """Keep the preview path text neatly truncated when the window is resized."""
        super().resizeEvent(event)
        self._refresh_preview_title_text()
        self._refresh_preview_path_text()

    def on_table_item_pressed(self, item):
        """Start a short fill animation for the clicked map."""
        if not item:
            return

        map_id = str(item.data(Qt.UserRole) or "").strip().upper()
        if not map_id:
            return

        # Prevent an immediate double launch from the same click event.
        if self.click_fill_timer.isActive() and self.click_fill_map_id == map_id and self.click_fill_progress < 0.18:
            return

        self.table.setCurrentItem(item)
        self.click_fill_map_id = map_id
        self.click_fill_progress = 0.0
        self.table.click_fill_map_id = map_id
        self.table.click_fill_progress = 0.0
        self.table.click_fill_armed = True
        if self.click_fill_timer.isActive():
            self.click_fill_timer.stop()
        self.click_fill_timer.start()
        self.table.viewport().update()

    def _advance_click_fill(self):
        """Advance the click fill animation."""
        self.click_fill_progress += self.CLICK_FILL_SPEED / 100.0
        if hasattr(self, "table"):
            self.table.click_fill_progress = self.click_fill_progress
            if self.click_fill_progress > 0.0:
                self.table.click_fill_armed = False

        if self.click_fill_progress >= 1.0:
            self.click_fill_progress = 0.0
            self.click_fill_map_id = ""
            if hasattr(self, "table"):
                self.table.click_fill_progress = 0.0
                self.table.click_fill_map_id = ""
                self.table.click_fill_armed = False
            self.click_fill_timer.stop()

        if hasattr(self, "table"):
            self.table.viewport().update()

    def _set_preview_title(self, title):
        """Set the full title text and refresh the visible truncated label."""
        clean_title = str(title or "No map selected").strip() or "No map selected"
        self.preview_title_full_text = clean_title
        self._refresh_preview_title_text()

    def _refresh_preview_title_text(self):
        """Display the title with ellipsis without widening the right panel."""
        if not hasattr(self, "preview_title"):
            return

        full_text = str(getattr(self, "preview_title_full_text", "No map selected") or "No map selected")
        self.preview_title.setToolTip(full_text if full_text != "No map selected" else "")

        metrics = QFontMetrics(self.preview_title.font())
        available_width = max(120, self.preview_title.width() - 6)
        elided = metrics.elidedText(full_text, Qt.TextElideMode.ElideRight, available_width)
        self.preview_title.setText(elided)

    def _set_preview_path(self, rel_path):
        """Set the full path text and refresh the visible truncated label."""
        clean_rel = str(rel_path or "-").strip() or "-"
        self.preview_path_full_text = f"Path: {clean_rel}"
        self._refresh_preview_path_text()

    def _refresh_preview_path_text(self):
        """Display the path with ellipsis without widening the right panel."""
        if not hasattr(self, "preview_path"):
            return

        full_text = str(getattr(self, "preview_path_full_text", "Path: -") or "Path: -")
        self.preview_path.setToolTip(full_text if full_text != "Path: -" else "")

        metrics = QFontMetrics(self.preview_path.font())
        available_width = max(120, self.preview_path.width() - 6)
        elided = metrics.elidedText(full_text, Qt.TextElideMode.ElideMiddle, available_width)
        self.preview_path.setText(elided)

    def populate_mods(self):
        """Load all mods grouped by category and build the menu."""
        # GUI title -> folder name
        categories = {
            "DOOM MODS": "doom",
            "HERETIC MODS": "heretic",
            "HEXEN MODS": "hexen",
            "WOLFENSTEIN MODS": "Wolfenstein"
        }

        has_any_mods = False

        for title, folder_name in categories.items():
            mod_dir = os.path.join(cfg.BASE_DIR, "mods", folder_name)
            
            # Skip folders that do not exist.
            if not os.path.exists(mod_dir):
                continue

            # Read mod subfolders.
            mod_folders = [d for d in os.listdir(mod_dir) if os.path.isdir(os.path.join(mod_dir, d))]

            # Skip empty categories.
            if not mod_folders:
                continue

            has_any_mods = True

            # Category header
            header = QLabel(title)
            if self.mod_layout.count() == 0:
                # First category without top spacing.
                header.setStyleSheet("font-weight: bold; color: #3498db; margin-bottom: 2px;")
            else:
                # Later categories with top spacing.
                header.setStyleSheet("font-weight: bold; color: #3498db; margin-top: 15px; margin-bottom: 2px;")
                
            self.mod_layout.addWidget(header)

            # Mod checkboxes
            for mod in sorted(mod_folders):
                cb = QCheckBox(mod)
                
                # Store the absolute mod path as a property.
                full_path = os.path.join(mod_dir, mod)
                cb.setProperty("mod_path", full_path)
                
                self.mod_layout.addWidget(cb)

        # Fallback for no installed mods.
        if not has_any_mods:
            lbl_empty = QLabel("No mods installed.")
            lbl_empty.setStyleSheet("color: gray; font-style: italic;")
            self.mod_layout.addWidget(lbl_empty)

    def load_data(self):
        """Load data from the database."""
        import dms_core.database as db
        self.all_maps_data = db.get_all_maps()

    def _filter_maps(self, maps):
        """Filter maps using the search field and quick filter."""
        if not hasattr(self, "map_search_input"):
            return maps

        needle = self.map_search_input.text().strip().lower()
        active_filter = str(getattr(self, "quick_filter", "ALLE") or "ALLE").upper()

        filtered = []
        for m in maps:
            if isinstance(m, dict):
                map_id = str(m.get("ID", "")).strip().upper()
                name = str(m.get("Name", "")).strip()
                iwad = str(m.get("IWAD", "")).strip().lower()
                kat = str(m.get("Kategorie", "")).strip().upper()
                fav = str(m.get("Favorite", "0")).strip()
                nomods = str(m.get("NoMods", "0")).strip()
                haystack = " ".join([
                    map_id,
                    name,
                    iwad,
                    kat,
                ]).lower()
            else:
                map_id = str(m[2]) if len(m) > 2 else ""
                name = str(m[3]) if len(m) > 3 else ""
                iwad = str(m[4]).lower() if len(m) > 4 else ""
                kat = str(m[8]).upper() if len(m) > 8 else "PWAD"
                fav = str(m[12]) if len(m) > 12 else "0"
                nomods = str(m[1]) if len(m) > 1 else "0"
                haystack = " ".join([
                    map_id,
                    name,
                    iwad,
                    kat,
                ]).lower()

            if active_filter == "DOOM":
                if ("heretic" in iwad) or ("hexen" in iwad) or ("strife" in iwad) or kat == "EXTRA":
                    continue
            elif active_filter == "HERETIC":
                if "heretic" not in iwad:
                    continue
            elif active_filter == "HEXEN":
                if "hexen" not in iwad:
                    continue
            elif active_filter == "FAVORIT":
                if fav != "1":
                    continue
            elif active_filter == "NOMODS":
                if nomods != "1":
                    continue

            if needle and needle not in haystack:
                continue

            filtered.append(m)

        return filtered

    def _extract_sort_fields(self, m):
        """Extract robust sort fields from dict and list-based map data."""
        if isinstance(m, dict):
            return {
                "id": str(m.get("ID", "")).strip().upper(),
                "name": str(m.get("Name", "")).strip().lower(),
                "favorite": str(m.get("Favorite", "0")).strip(),
                "last_played": str(m.get("LastPlayed", "")).strip(),
            }

        return {
            "id": str(m[2]).strip().upper() if len(m) > 2 else "",
            "name": str(m[3]).strip().lower() if len(m) > 3 else "",
            "favorite": str(m[12]).strip() if len(m) > 12 else "0",
            "last_played": str(m[10]).strip() if len(m) > 10 else "",
        }

    def _parse_last_played(self, value):
        """Parse LastPlayed robustly; empty values are treated as very old."""
        txt = str(value or "").strip()
        if not txt or txt == "-":
            return datetime.min
        try:
            return datetime.strptime(txt, "%Y-%m-%d %H:%M")
        except Exception:
            return datetime.min

    def _apply_sort(self, maps):
        """Sort the filtered map list according to the active selection."""
        mode = str(getattr(self, "sort_mode", "insert") or "insert")
        items = list(maps)

        if mode == "insert":
            return items
        if mode == "newest":
            return list(reversed(items))
        if mode == "name_asc":
            return sorted(items, key=lambda m: self._extract_sort_fields(m)["name"])
        if mode == "fav_first":
            return sorted(items, key=lambda m: (self._extract_sort_fields(m)["favorite"] != "1", self._extract_sort_fields(m)["name"]))
        if mode == "last_played":
            return sorted(items, key=lambda m: self._parse_last_played(self._extract_sort_fields(m)["last_played"]), reverse=True)
        return items

    def on_sort_mode_changed(self, _index=None):
        """Save the selected sort mode and refresh the table."""
        if not hasattr(self, "cmb_sort"):
            return
        self.sort_mode = str(self.cmb_sort.currentData() or "insert")
        cfg.update_config_value("SETTINGS", "map_sort_mode", self.sort_mode)
        self.refresh_data()

    def set_quick_filter(self, filter_key, persist=True):
        """Activate a quick filter chip and refresh the list."""
        key = str(filter_key or "ALLE").upper()
        if key not in getattr(self, "quick_filter_buttons", {}):
            key = "ALLE"

        self.quick_filter = key
        for btn_key, btn in self.quick_filter_buttons.items():
            btn.setChecked(btn_key == key)

        if persist:
            cfg.update_config_value("SETTINGS", "map_quick_filter", key)
        self.refresh_data()

    def get_checked_mods(self):
        """Scan the mod layout and return a list of checked mod paths."""
        selected_mods = []
        
        # Inspect all widgets in the mod layout.
        for i in range(self.mod_layout.count()):
            widget = self.mod_layout.itemAt(i).widget()
            
            # Only process checked checkboxes.
            if isinstance(widget, QCheckBox) and widget.isChecked():
                
                # Read the stored mod path.
                mod_path = widget.property("mod_path")
                
                if mod_path:
                    selected_mods.append(mod_path)
                
        return selected_mods

    @tracker
    def run_selected_map(self, item=None):
        """Start the selected map while respecting mod locks and debug mode."""
        # Determine the target cell.
        cell = item if item else self.table.currentItem()
        if not cell:
            QMessageBox.warning(self, "Cancelled", "Please select a map from the list first.")
            return

        # Load map ID and data.
        mid = cell.data(Qt.UserRole)
        if not mid:
            QMessageBox.warning(self, "Error", "Could not determine the selected map ID.")
            return

        map_data = db.get_map_by_id(mid)
        if not map_data:
            QMessageBox.critical(self, "Error", "Could not load the map data.")
            return

        # Check the active engine.
        active_engine_name = cfg.get_current_engine()
        
        if not active_engine_name:
            QMessageBox.critical(self, "Error", "No engine selected. Open Engine Manager and activate a port first.")
            return

        # Build the engine EXE path.
        engine_path = os.path.join(cfg.ENGINE_BASE_DIR, active_engine_name, f"{active_engine_name}.exe")
        
        if not os.path.exists(engine_path):
            QMessageBox.critical(self, "Error", f"Engine executable not found:\n{engine_path}")
            return

        try:
            # Read selected mods.
            selected_mods = self.get_checked_mods()
            
            # Evaluate mod lock state.
            is_mod_locked = str(map_data.get('NoMods', '0')) == "1"
            if is_mod_locked:
                print(f"🚫 MOD LOCK ACTIVE for {map_data.get('Name')}")
                selected_mods = []

            # Build the start command.
            debug_info = runner.get_start_command(engine_path, map_data, selected_mods)
            
            # Optional debug dialog.
            if self.cb_debug.isChecked():
                cmd_str = ' '.join(debug_info.get('cmd', []))
                
                # Mod status for debug output.
                mod_status_text = (
                    "<span style='color: #e74c3c;'>DISABLED (mod lock active)</span>"
                    if is_mod_locked else f"<span style='color: #2ecc71;'>{len(selected_mods)} loaded</span>"
                )
                
                debug_msg = (
                    f"<b>ENGINE:</b><br>{active_engine_name}<br><br>"
                    f"<b>COMMAND (CMD):</b><br><code style='color: #2ecc71;'>{cmd_str}</code><br><br>"
                    f"<b>MOD STATUS:</b> {mod_status_text}<br><br>"
                    f"<b>YOUR PARAMETERS (ARGS):</b><br><span style='color: #e74c3c;'>{map_data.get('ARGS', '-')}</span>"
                )
                
                msg_box = QMessageBox(self)
                msg_box.setWindowTitle("DMS Debug Menu")
                msg_box.setTextFormat(Qt.TextFormat.RichText)
                msg_box.setText(debug_msg)
                msg_box.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
                msg_box.button(QMessageBox.StandardButton.Ok).setText("Start")
                
                if msg_box.exec() == QMessageBox.StandardButton.Cancel:
                    return

            # Start the game.
            print(f"🚀 Starting game: {map_data.get('Name')} with engine: {active_engine_name}...")
            success = runner.run_game(engine_path, map_data, selected_mods)

            if success:
                self.update_stats()
            else:
                QMessageBox.warning(self, "Launch Failed", "The game could not be started. Check the console/logs.")

        except Exception as e:
            print(f"❌ CRASH in run_selected_map: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Crash", f"Error during launch attempt:\n{str(e)}")

    def show_context_menu(self, pos):
        """Create a clean right-click menu without ghost effects."""
        item = self.table.itemAt(pos)
        if not item: return
        
        mid = item.data(Qt.UserRole)
        if not mid: return

        # Create context menu.
        menu = QMenu(self.table)
        
        # Define actions.
        act_clear = menu.addAction("✔ Map Clear")
        act_mod   = menu.addAction("🅼 Skip Mods")
        menu.addSeparator()
        act_args  = menu.addAction("🛠 Edit Parameters (ARGS)")
        act_del   = menu.addAction("🗑 Delete Map")

        # Show the menu and read the selection.
        action = menu.exec(self.table.mapToGlobal(pos))

        # Process the selection.
        if action == act_clear:
            db.toggle_map_clear(mid)
            self.refresh_data()
            
        elif action == act_mod:
            db.toggle_mod_skip(mid)
            self.refresh_data()
            
        elif action == act_args:
            # Use the existing parameter editing function.
            if hasattr(self, 'edit_map_args'):
                self.edit_map_args(mid)
            elif hasattr(self, 'edit_args'):
                self.edit_args(mid)
                
        elif action == act_del:
            self.delete_map(mid)

    def edit_map_parameters(self, row=None):
        
        # Read the current cell.
        current_cell = self.table.currentItem()
        if not current_cell: 
            return
            
        map_id = current_cell.data(Qt.UserRole)
        if not map_id:
            return
            
        map_data = db.get_map_by_id(map_id)
        selected_mods = self.get_checked_mods()
        
        # Check the mod lock.
        if str(map_data.get('NoMods', '0')) == "1":
            print("🚫 MOD LOCK: Starting without mods.")
            selected_mods = []
        if not map_data:
            return
            
        current_args = map_data.get('ARGS', '')
        map_name = map_data.get('Name', 'Unknown')

        # Show the ARGS dialog.
        new_args, ok = QInputDialog.getText(
            self, "Set Parameters",
            f"Additional launch parameters for '{map_name}':",
            QLineEdit.EchoMode.Normal, current_args
        )

        if ok:
            if hasattr(db, 'update_map_args'):
                db.update_map_args(map_id, new_args)
                QMessageBox.information(self, "Saved", f"Parameters updated:\n{new_args}")
                self.refresh_data()
            else:
                QMessageBox.warning(self, "Error", "The save function is missing in database.py.")

    def create_item(self, m):
            # Create an empty non-selectable cell.
            if not m: 
                item = QTableWidgetItem("")
                item.setFlags(Qt.ItemFlag.NoItemFlags) 
                return item
            
            # Read data from dict or list format.
            try:
                if isinstance(m, dict) or hasattr(m, "keys"):
                    # Dict format
                    c_flag = str(m.get("Cleared", "0")).strip()
                    m_flag = str(m.get("NoMods", "0")).strip()
                    mid    = str(m.get("ID", "")).strip().upper()
                    name   = str(m.get("Name", "")).strip()
                    iwad   = str(m.get("IWAD", "")).strip().lower()
                    f_flag = str(m.get("Favorite", "0")).strip()
                    n_flag = "1" if self._is_recent_install(mid) else "0"
                else:
                    # List format
                    if len(m) < 4:
                        raise ValueError("Zu wenig Daten")
                    c_flag = str(m[0]).strip()
                    m_flag = str(m[1]).strip()
                    mid    = str(m[2]).strip().upper() 
                    name   = str(m[3]).strip()
                    iwad   = str(m[4]).strip().lower()
                    f_flag = str(m[12]).strip() if len(m) > 12 else "0"
                    n_flag = "1" if self._is_recent_install(mid) else "0"
            except (KeyError, IndexError, ValueError):
                # Treat invalid data as an empty row.
                item = QTableWidgetItem("")
                item.setFlags(Qt.ItemFlag.NoItemFlags) 
                return item

            # Without an ID the cell must not be selectable.
            if not mid:
                item = QTableWidgetItem("")
                item.setFlags(Qt.ItemFlag.NoItemFlags) 
                return item

            # Text only; badges are rendered by the delegate.
            display = name if name and name != "-" else mid

            item = QTableWidgetItem(display)
            item.setData(Qt.UserRole, mid)
            item.setData(Qt.UserRole + 1, {"n": n_flag, "c": c_flag, "f": f_flag, "m": m_flag, "iwad": iwad})

            return item

    def _set_preview_tag_style(self, iwad, category):
        """Apply a color code by game type in the preview."""
        iwad_l = str(iwad or "").lower()
        cat_u = str(category or "").upper()

        if "heretic" in iwad_l:
            text, bg = "HERETIC", "#b7950b"
        elif "hexen" in iwad_l:
            text, bg = "HEXEN", "#7d3c98"
        elif "strife" in iwad_l:
            text, bg = "STRIFE", "#2471a3"
        elif cat_u == "IWAD":
            text, bg = "OFFICIAL", "#2d6a4f"
        else:
            text, bg = "DOOM", "#c0392b"

        self.preview_tag.setText(text)
        self.preview_tag.setStyleSheet(f"background-color: {bg}; color: #ffffff; border-radius: 10px; font-size: 11px; font-weight: bold; padding: 0 8px;")

    def update_map_preview(self):
        """Update the preview panel based on the currently selected map."""
        if not hasattr(self, "preview_title"):
            return

        selected_items = self.table.selectedItems()
        target_item = None

        for item in selected_items:
            if item and item.data(Qt.UserRole):
                target_item = item
                break

        if not target_item:
            current = self.table.currentItem()
            if current and current.data(Qt.UserRole):
                target_item = current

        if not target_item:
            self._set_preview_title("No map selected")
            self.preview_tag.setText("-")
            self.preview_tag.setStyleSheet("background-color: #3a3a3a; color: #dcdcdc; border-radius: 10px; font-size: 11px; padding: 0 8px;")
            self.preview_meta.setText("ID: -\nIWAD: -\nCategory: -")
            self.preview_play.setText("Playtime: 0 min\nLast Played: -")
            self._set_preview_path("-")
            return

        map_id = str(target_item.data(Qt.UserRole)).strip().upper()
        map_data = db.get_map_by_id(map_id)
        if not map_data:
            return

        name = str(map_data.get("Name", "") or map_id)
        iwad = str(map_data.get("IWAD", "-")).strip()
        kategorie = str(map_data.get("Kategorie", "-")).strip().upper()
        playtime = str(map_data.get("Playtime", "0")).strip() or "0"
        last_played = str(map_data.get("LastPlayed", "-")).strip() or "-"
        rel_path = str(map_data.get("Path", "-")).strip() or "-"

        self._set_preview_title(name)
        self._set_preview_tag_style(iwad, kategorie)
        self.preview_meta.setText(f"ID: {map_id}\nIWAD: {iwad}\nCategory: {kategorie}")
        self.preview_play.setText(f"Playtime: {playtime} min\nLast Played: {last_played}")
        self._set_preview_path(rel_path)

    def refresh_data(self):
        """Refresh the map table using database data."""
        self.load_data()
        
        try:
            # Load, filter, and sort data.
            all_m = db.get_all_maps()
            all_m = self._filter_maps(all_m)
            all_m = self._apply_sort(all_m)
            
            # Prepare target columns.
            blocks = {1: [], 2: [], 3: [], 4: [], 5: []}
            doom_maps = []
            
            # Group the extra column by game.
            heretic_maps = []
            hexen_maps = []
            strife_maps = []
            extra_misc_maps = []

            for m in all_m:
                # Read IWAD/category robustly.
                iwad = str(m.get("IWAD", "")).lower() if isinstance(m, dict) else str(m[4]).lower()
                kat = str(m.get("Kategorie", "PWAD")).upper() if isinstance(m, dict) else str(m[8]).upper()

                # EXTRA category always goes in column 5.
                if kat == "EXTRA":
                    if "heretic" in iwad:
                        heretic_maps.append(m)
                    elif "hexen" in iwad:
                        hexen_maps.append(m)
                    elif "strife" in iwad:
                        strife_maps.append(m)
                    else:
                        extra_misc_maps.append(m)
                    continue
                
                # Group game types into column 5.
                if "heretic" in iwad:
                    heretic_maps.append(m)
                elif "hexen" in iwad:
                    hexen_maps.append(m)
                elif "strife" in iwad:
                    strife_maps.append(m)
                else:
                    # Treat the rest as DOOM.
                    doom_maps.append(m)

            # Build column 5 with separator rows.
            if heretic_maps:
                blocks[5].extend(heretic_maps)
                
            if hexen_maps:
                # Separator row between groups.
                if blocks[5]: 
                    blocks[5].append([]) 
                blocks[5].extend(hexen_maps)
                
            if strife_maps:
                # Separator row between groups.
                if blocks[5]:
                    blocks[5].append([])
                blocks[5].extend(strife_maps)

            if extra_misc_maps:
                if blocks[5]:
                    blocks[5].append([])
                blocks[5].extend(extra_misc_maps)
            # Distribute DOOM maps across columns 1 to 4.
            per_col = (len(doom_maps) + 3) // 4
            blocks[1] = doom_maps[:per_col]
            blocks[2] = doom_maps[per_col:per_col * 2]
            blocks[3] = doom_maps[per_col * 2:per_col * 3]
            blocks[4] = doom_maps[per_col * 3:]

            # Determine row count.
            max_rows = max(len(blocks[1]), len(blocks[2]), len(blocks[3]), len(blocks[4]), len(blocks[5]))
            self.table.setRowCount(max_rows)

            # Fill the table.
            for i in range(max_rows):
                item1 = self.create_item(blocks[1][i]) if i < len(blocks[1]) else self.create_item([])
                item2 = self.create_item(blocks[2][i]) if i < len(blocks[2]) else self.create_item([])
                item3 = self.create_item(blocks[3][i]) if i < len(blocks[3]) else self.create_item([])
                item4 = self.create_item(blocks[4][i]) if i < len(blocks[4]) else self.create_item([])
                item5 = self.create_item(blocks[5][i]) if i < len(blocks[5]) else self.create_item([])
                
                self.table.setItem(i, 0, item1)
                self.table.setItem(i, 1, item2)
                self.table.setItem(i, 2, item3)
                self.table.setItem(i, 3, item4)
                self.table.setItem(i, 4, item5)

        except Exception as e:
            print(f"Error while loading the table: {e}")

        # Focus an optionally queued target map.
        if self.pending_focus_map_id:
            target_id = self.pending_focus_map_id
            self.pending_focus_map_id = None
            if self._focus_map_in_table(target_id):
                self.statusBar().showMessage(f"New map found: {target_id}", 7000)
            else:
                self.statusBar().showMessage(f"Map {target_id} was installed, but it could not be focused directly.", 7000)

        if hasattr(self, "preview_title"):
            self.update_map_preview()

        self.update_stats()

    def update_stats(self):
        """Update the dashboard using the 0/1 flag system."""
        try:
            all_m = db.get_all_maps()
            total = len(all_m)
            cleared = sum(1 for m in all_m if str(m.get("Cleared", "0")) == "1")
            favorites = sum(1 for m in all_m if str(m.get("Favorite", "0")) == "1")
            new_count = sum(1 for m in all_m if self._is_recent_install(m.get("ID", "")))
            clear_percent = int((cleared / total) * 100) if total > 0 else 0
            
            if hasattr(self, 'stat_count'):
                self.stat_count.setText(f"📂 MAPS: {total}")
                self.stat_cleared.setText(f"✅ CLEAR: {cleared} ({clear_percent}%)")
                self.stat_favorites.setText(f"⭐ FAV: {favorites}")
                self.stat_new.setText(f"🆕 NEW: {new_count}")
                
                total_sec = db.get_total_seconds()
                h, r = divmod(int(total_sec), 3600)
                m, _ = divmod(r, 60)
                self.stat_playtime.setText(f"🕒 TIME: {h}H {m}M")
                
                eng = str(cfg.CURRENT_ENGINE).upper() if cfg.CURRENT_ENGINE else "NONE"
                self.stat_engine.setText(f"⚙️ ENGINE: {eng}")

                needle = self.map_search_input.text().strip() if hasattr(self, "map_search_input") else ""
                filter_name = str(getattr(self, "quick_filter", "ALLE") or "ALLE")
                filter_name = {"ALLE": "ALL", "FAVORIT": "FAVORITES", "NOMODS": "MOD LOCKED"}.get(filter_name, filter_name)
                if needle:
                    self.stat_view.setText(f"🔎 VIEW: {filter_name} | Search: {needle}")
                else:
                    self.stat_view.setText(f"🔎 VIEW: {filter_name}")
        except Exception as e:
            print(f"❌ Stats error: {e}")

    def get_selected_id(self):
        """Return the hidden ID from the currently selected cell."""
        item = self.table.currentItem()
        if item:
            return item.data(Qt.UserRole)
        return None

    def on_cell_double_clicked(self, row, column):
        """Start the game when a cell is double-clicked."""
        map_id = self.get_selected_id()
        if map_id:
            self.run_game(map_id)

# ============================================================================
# Core functions (play and install)
# ============================================================================

    def run_game(self, map_id):
        """Legacy wrapper: start a map by ID using the current runner API."""
        if not map_id:
            return

        map_data = db.get_map_by_id(map_id)
        if not map_data:
            QMessageBox.warning(self, "Error", f"Map {map_id} was not found.")
            return

        active_engine_name = cfg.get_current_engine()
        if not active_engine_name:
            QMessageBox.critical(self, "Error", "No engine selected. Open Engine Manager and activate a port first.")
            return

        engine_path = os.path.join(cfg.ENGINE_BASE_DIR, active_engine_name, f"{active_engine_name}.exe")
        if not os.path.exists(engine_path):
            QMessageBox.critical(self, "Error", f"Engine executable not found:\n{engine_path}")
            return

        selected_mods = self.get_checked_mods()
        if str(map_data.get('NoMods', '0')) == "1":
            selected_mods = []

        try:
            self.statusBar().showMessage(f"Starting {map_data.get('Name', map_id)}...")
            success = runner.run_game(engine_path, map_data, selected_mods)
            if success:
                self.refresh_data()
            else:
                QMessageBox.warning(self, "Launch Failed", "The game could not be started. Check the console/logs.")
        except Exception as e:
            QMessageBox.critical(self, "Critical Error", f"Workflow error:\n{str(e)}")
                
    def run_installer(self):
        """Install a Doomworld download or import local files from Install/."""
        selected_row = self.table.currentRow()
        
        if selected_row >= 0:
            item = self.table.item(selected_row, 0)
            map_data = item.data(Qt.UserRole)
            
            if map_data and isinstance(map_data, dict):
                # Doomworld download/install
                title = map_data.get('title', 'Unbekannt')
                before_ids = self._capture_map_ids()

                # Progress popup so user knows the download started
                wait_dlg = QDialog(self)
                wait_dlg.setWindowTitle("Installing...")
                wait_dlg.setModal(True)
                wait_dlg.setFixedSize(380, 110)
                wait_layout = QVBoxLayout(wait_dlg)
                wait_label = QLabel(f"\u2b07  Downloading and installing:\n\n  {title}\n\nPlease wait...")
                wait_label.setWordWrap(True)
                wait_layout.addWidget(wait_label)
                wait_dlg.show()
                QApplication.processEvents()

                def _update(m):
                    self.statusBar().showMessage(m)
                    wait_label.setText(f"\u2b07  {m}")
                    QApplication.processEvents()

                success, _ = api.download_idgames_gui(map_data, callback=_update)
                wait_dlg.close()
                if success:
                    self._mark_new_maps_from_diff(before_ids)
                    self.refresh_data()
                    QMessageBox.information(self, "Success", f"'{title}' installed.")
                return

        self.run_install_scan(show_empty_message=True, auto_mode=False)

    def run_install_scan(self, show_empty_message=True, auto_mode=False):
        """Import all compatible files from Install/ with optional user confirmation."""
        candidates = installer.get_install_candidates()
        if not candidates:
            if show_empty_message:
                self.statusBar().showMessage("No new files were found in the 'Install' folder.", 6000)
            return 0

        if not auto_mode:
            reply = QMessageBox.question(
                self,
                "Install Folder Scan",
                f"Found {len(candidates)} importable file(s) in Install/.\nStart import now?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if reply != QMessageBox.Yes:
                return 0

        before_ids = self._capture_map_ids()
        self.statusBar().showMessage("Scanning the 'Install' folder for new maps...")

        count = installer.install_from_folder(
            callback=lambda m: self.statusBar().showMessage(m),
            resolve_game=self.prompt_install_game_profile,
        )

        if count > 0:
            self._mark_new_maps_from_diff(before_ids)
            self.refresh_data()
            if auto_mode:
                self.statusBar().showMessage(f"Startup scan imported {count} map(s) from Install/.", 7000)
            else:
                QMessageBox.information(self, "Auto Installer", f"Successfully imported {count} map(s) from the Install folder.")
        elif show_empty_message and not auto_mode:
            self.statusBar().showMessage("No new files were found in the 'Install' folder.", 6000)

        return count

    def prompt_install_game_profile(self, file_path):
        """Fallback dialog: ask for the base game when no TXT IWAD info is found."""
        fname = os.path.basename(str(file_path))
        options = [
            "DOOM (doom.wad)",
            "DOOM II (doom2.wad)",
            "HERETIC (heretic.wad)",
            "HEXEN (hexen.wad)",
        ]

        selected, ok = QInputDialog.getItem(
            self,
            "Choose Base Game",
            f"No TXT-based IWAD info was found for:\n{fname}\n\nWhich base game is this add-on for?",
            options,
            1,
            False,
        )

        if not ok:
            return None

        mapping = {
            "DOOM (doom.wad)": "doom",
            "DOOM II (doom2.wad)": "doom2",
            "HERETIC (heretic.wad)": "heretic",
            "HEXEN (hexen.wad)": "hexen",
        }
        return mapping.get(selected)

    def add_map_manually(self):
        """Add a map manually to the database."""
        title, ok = QInputDialog.getText(self, "Add Map Manually", "Map name:")
        if not ok:
            return

        title = str(title).strip()
        if not title:
            QMessageBox.warning(self, "Missing Input", "Please enter a map name.")
            return

        game_options = ["DOOM", "HERETIC", "HEXEN", "WOLF", "EXTRA"]
        game, ok = QInputDialog.getItem(self, "Game Profile", "Profile for ID generation:", game_options, 0, False)
        if not ok:
            return

        iwad_defaults = {
            "DOOM": "doom2.wad",
            "HERETIC": "heretic.wad",
            "HEXEN": "hexen.wad",
            "WOLF": "doom2.wad",
            "EXTRA": "doom.wad",
        }
        iwad_default = iwad_defaults.get(game, "doom2.wad")
        iwad, ok = QInputDialog.getText(self, "IWAD", "IWAD file (for example doom2.wad):", text=iwad_default)
        if not ok:
            return

        iwad = str(iwad).strip()
        if not iwad:
            QMessageBox.warning(self, "Missing Input", "Please enter an IWAD.")
            return

        path_rel, ok = QInputDialog.getText(
            self,
            "PWAD Path",
            "Path under pwad (folder name or file):",
        )
        if not ok:
            return

        path_rel = str(path_rel).strip()
        if not path_rel:
            QMessageBox.warning(self, "Missing Input", "Please enter a path under pwad.")
            return

        kategorie_options = ["PWAD", "EXTRA", "IWAD"]
        kategorie, ok = QInputDialog.getItem(self, "Category", "Choose category:", kategorie_options, 0, False)
        if not ok:
            return

        args, ok = QInputDialog.getText(self, "Launch Parameters", "Optional ARGS (leave empty for none):", text="0")
        if not ok:
            return
        args = str(args).strip() or "0"

        prefix = str(game).upper()
        if prefix == "WOLF":
            prefix = "WOLF"
        new_id = db.get_next_id(prefix=prefix)

        custom_id, ok = QInputDialog.getText(self, "Map ID", "ID (leave empty = automatic):", text=new_id)
        if not ok:
            return
        custom_id = str(custom_id).strip().upper() or new_id

        map_data = {
            "Cleared": "0",
            "NoMods": "0",
            "ID": custom_id,
            "Name": title,
            "IWAD": iwad,
            "Path": path_rel,
            "MOD": "0",
            "ARGS": args,
            "Kategorie": kategorie,
            "Playtime": "0",
            "LastPlayed": "-",
            "RemoteID": "0",
            "Favorite": "0",
        }

        if db.insert_map(map_data):
            self.set_pending_focus_map(custom_id)
            self.refresh_data()
            QMessageBox.information(self, "Success", f"Map '{title}' was added as {custom_id}.")
        else:
            QMessageBox.warning(self, "Error", "The map could not be added. Check whether the ID already exists.")

    def play_random(self):
        """Called when the random button is pressed."""
        visible_map_ids = []

        for row in range(self.table.rowCount()):
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                if not item:
                    continue

                map_id = str(item.data(Qt.UserRole) or "").strip().upper()
                if map_id:
                    visible_map_ids.append((map_id, item))

        if not visible_map_ids:
            QMessageBox.information(self, "No Map Available", "There is currently no visible map available for random selection.")
            return

        selected_map_id, selected_item = random.choice(visible_map_ids)
        self.table.setCurrentItem(selected_item)
        self.table.scrollToItem(selected_item, QAbstractItemView.ScrollHint.PositionAtCenter)

        self.run_game(selected_map_id)

    def check_updates(self):
        """Check for launcher updates in the background."""
        update_info = updater.check_launcher_update()
        if update_info.get("error"):
            self.statusBar().showMessage(f"Update check error: {update_info.get('error')}", 7000)
            return

        if update_info.get("update_available"):
            dlg = QDialog(self)
            dlg.setWindowTitle("Update Available")
            dlg.setModal(True)
            dlg.resize(760, 560)

            layout = QVBoxLayout(dlg)
            headline = QLabel(
                f"Version {update_info['remote_version']} is available.\n"
                "Please read the changelog first and then decide whether you want to update."
            )
            headline.setWordWrap(True)
            layout.addWidget(headline)

            changelog = QTextEdit()
            changelog.setReadOnly(True)
            changelog_text = str(update_info.get("changelog_text") or "").strip()
            if changelog_text:
                changelog.setPlainText(changelog_text)
            else:
                changelog.setPlainText("No changelog was loaded. You can still continue with the update.")
            layout.addWidget(changelog)

            btn_row = QHBoxLayout()
            btn_open = QPushButton("Open Changelog")
            btn_no = QPushButton("Later")
            btn_yes = QPushButton("Update Now")

            changelog_url = str(update_info.get("changelog_url") or "").strip()
            btn_open.setEnabled(bool(changelog_url))
            if changelog_url:
                btn_open.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(changelog_url)))

            btn_no.clicked.connect(dlg.reject)
            btn_yes.clicked.connect(dlg.accept)

            btn_row.addWidget(btn_open)
            btn_row.addStretch()
            btn_row.addWidget(btn_no)
            btn_row.addWidget(btn_yes)
            layout.addLayout(btn_row)

            if dlg.exec() == QDialog.Accepted:
                mode = str(update_info.get("update_mode") or "script")
                self.create_guard_backup(f"preupdate_v{cfg.APP_VERSION}")
                if mode == "package":
                    ok = updater.apply_launcher_package_update(update_info)
                else:
                    ok = updater.apply_launcher_update(update_info['remote_version'], update_info['remote_code'])

                if ok:
                    QMessageBox.information(self, "Update", "Update completed successfully. The launcher will now close. Please restart it.")
                    sys.exit(0)
                QMessageBox.warning(self, "Update", "The update could not be applied. Check the logs and use rollback if needed.")

    # --- Menus and dialogs ---

    def show_context_menu(self, pos):
        """Create the right-click menu."""
        item = self.table.itemAt(pos)
        if not item: return

        # Read the map ID from the cell.
        mid = item.data(Qt.UserRole)
        if not mid: return

        menu = QMenu(self.table)

        # 1. Define actions
        act_clear = menu.addAction("✔ Map Clear")
        act_mod   = menu.addAction("🅼 Skip Mods")
        act_fav   = menu.addAction("⭐ Favorite")
        act_rename = menu.addAction("✏ Rename Map")
        
        menu.addSeparator()
        act_args  = menu.addAction("🛠 Edit Parameters")
        act_del   = menu.addAction("🗑 Delete Map")

        # 2. Show the menu
        action = menu.exec(self.table.mapToGlobal(pos))

        # 3. Process the clicked action
        if action == act_clear:
            db.toggle_map_clear(mid)
            self.refresh_data()
            
        elif action == act_mod:
            db.toggle_mod_skip(mid)
            self.refresh_data()

        elif action == act_fav:
            db.toggle_favorite(mid)
            self.statusBar().showMessage(f"Favorite status changed for {mid}.")
            self.refresh_data()

        elif action == act_rename:
            self.rename_map(mid)
            
        elif action == act_args:
            if hasattr(self, 'edit_map_parameters'):
                self.edit_map_parameters(mid)
                
        elif action == act_del:
            self.delete_map(mid)

    def delete_map(self, map_id):
        """Delete a database entry including related files in the PWAD path."""
        reply = QMessageBox.question(self, "Delete", f"Do you really want to delete map {map_id} including its files?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.create_guard_backup(f"predelete_{map_id}")
            if db.uninstall_map(map_id):
                QMessageBox.information(self, "Deleted", "Map removed successfully.")
                self.refresh_data()
            else:
                QMessageBox.warning(self, "Error", "The map could not be deleted (base game entry?).")

    def rename_map(self, map_id):
        """Rename the map title in the database."""
        map_data = db.get_map_by_id(map_id)
        if not map_data:
            QMessageBox.warning(self, "Error", "The map was not found.")
            return

        current_name = str(map_data.get("Name", "")).strip() or str(map_id)
        new_name, ok = QInputDialog.getText(
            self,
            "Rename Map",
            f"New name for {map_id}:",
            text=current_name,
        )

        if not ok:
            return

        final_name = str(new_name).strip()
        if not final_name:
            QMessageBox.warning(self, "Invalid Name", "The name cannot be empty.")
            return

        if final_name == current_name:
            return

        if db.update_map_name(map_id, final_name):
            self.statusBar().showMessage(f"Map {map_id} renamed to '{final_name}'.", 5000)
            self.refresh_data()
        else:
            QMessageBox.warning(self, "Error", "The name could not be saved.")

    def open_api(self):
        """Open the Doomworld browser and refresh after a successful download."""
        dlg = ApiBrowserDialog(self)
        dlg.main_refresh_signal.connect(self.refresh_data)
        dlg.exec()

    def open_db_viewer(self):
        """Open the DB viewer for filtering and exporting maps.db."""
        dlg = DatabaseViewerDialog(self)
        dlg.exec()

    def update_tracker_button_text(self):
        """Update the ON/OFF text of the tracker toggle."""
        tracker_on = cfg.config.getboolean("SETTINGS", "tracker_enabled", fallback=False)
        self.btn_tracker_toggle.setText("🐞 Debugger: ON" if tracker_on else "🐞 Debugger: OFF")

    def toggle_tracker(self):
        """Toggle the function tracker in config.ini."""
        current = cfg.config.getboolean("SETTINGS", "tracker_enabled", fallback=False)
        new_value = "False" if current else "True"
        cfg.update_config_value("SETTINGS", "tracker_enabled", new_value)

        if new_value == "False":
            legacy_tracker_log = os.path.join(cfg.BASE_DIR, "dms_tracker.log")
            if os.path.exists(legacy_tracker_log):
                try:
                    os.remove(legacy_tracker_log)
                except Exception:
                    pass

        self.update_tracker_button_text()
        state = "enabled" if new_value == "True" else "disabled"
        self.statusBar().showMessage(f"Debugger {state}.", 5000)

    def open_eng(self):
        """Open Engine Manager and refresh the GUI afterwards."""
        dialog = EngineManagerDialog(self)
        dialog.exec() 
        
        cfg.CURRENT_ENGINE = cfg.get_current_engine() 
        
        self.refresh_data()

    def edit_map_parameters(self, map_id):
        """Open a dialog to edit custom map parameters (ARGS)."""

        # 1. Load current data directly from the database.
        map_data = db.get_map_by_id(map_id)
        if not map_data:
            QMessageBox.warning(self, "Error", "Could not load the map data.")
            return

        map_name = map_data.get('Name', 'Unknown')
        current_args = str(map_data.get('ARGS', '0')).strip()
        
        # If the database stores "0", present an empty field to the user.
        if current_args == "0":
            current_args = ""

        # 2. Show the input prompt.
        new_args, ok = QInputDialog.getText(
            self, 
            "Edit Parameters",
            f"Enter additional engine parameters for '{map_name}':\n(Example: -fast -nomonsters)\n\nLeave empty to remove parameters.",
            text=current_args
        )

        if ok:
            final_args = new_args.strip() if new_args.strip() else "0"
            
            if db.update_map_args(map_id, final_args):
                print(f"✅ Parameters saved for {map_id}: {final_args}")
            else:
                QMessageBox.warning(self, "Error", "The parameters could not be saved.")

# ============================================================================
# Startup
# ============================================================================
if __name__ == "__main__":
    # 1. Run silent setup (folders, config.ini, and database scaffold).
    init.run_initial_setup()

    # Windows taskbar identity: prevents grouping under the Python icon.
    if sys.platform.startswith("win"):
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Apenotis.DMS.GUI")
        except Exception:
            pass

    # 2. Start the GUI.
    app = QApplication(sys.argv)
    icon_path = os.path.join(cfg.BASE_DIR, "assets", "dms_icon.ico")
    if not os.path.exists(icon_path):
        icon_path = os.path.join(cfg.BASE_DIR, "assets", "dms_icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    
    # Enable the dark theme, which fits the Doom aesthetic better.
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

    fail_info = updater.get_start_failure_info()
    if fail_info:
        backups = updater.get_update_backups()
        if backups:
            preview = str(fail_info.get("details", "") or "").strip()
            preview = preview[:700]
            txt = (
                "A problem was detected during the last start.\n"
                "Do you want to restore the latest update backup?"
            )
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Warning)
            msg.setWindowTitle("Startup Problem Detected")
            msg.setText(txt)
            if preview:
                msg.setDetailedText(preview)
            msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            msg.setDefaultButton(QMessageBox.Yes)
            if msg.exec() == QMessageBox.Yes:
                if updater.restore_latest_update_backup():
                    QMessageBox.information(None, "Rollback", "Backup restored successfully. Please restart the launcher.")
                    sys.exit(0)
                QMessageBox.warning(None, "Rollback", "The backup could not be restored.")
        updater.clear_start_failure_marker()

    # 3. Create and show the main window.
    window = DoomManagerGUI()
    if os.path.exists(icon_path):
        window.setWindowIcon(QIcon(icon_path))
    window.show()
    updater.clear_start_failure_marker()
    sys.exit(app.exec())