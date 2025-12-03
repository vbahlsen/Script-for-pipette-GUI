import sys
import os
import csv
import pathlib
import datetime
import json
import math
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QLabel, QScrollArea, QGridLayout, 
                               QFrame, QMessageBox, QPushButton, QStackedWidget,
                               QSizePolicy, QFileDialog)
from PySide6.QtCore import Qt, QSize, QRect, Signal, QTimer
from PySide6.QtGui import QPainter, QColor, QBrush, QPen, QFont, QPixmap

# Add the parent directory to sys.path to import gui_widgets
current_dir = pathlib.Path(__file__).resolve().parent
sys.path.append(str(current_dir))

from gui_widgets import WellPlateWidget

class LogParser:
    @staticmethod
    def parse_file(filepath):
        """
        Parses a pipetting log CSV file.
        Returns a dictionary with metadata and a dictionary of well data.
        """
        metadata = {}
        well_data = {}
        source_usage = {} # Map src_pos -> {status: 'ok'/'error', target_pos: pos}
        
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                reader = csv.reader(f)
                rows = list(reader)
                
                if len(rows) < 3:
                    return None
                
                # Parse metadata from row 2 (index 1)
                header = rows[0]
                meta_row = rows[1]
                
                col_map = {name: i for i, name in enumerate(header)}
                
                if "SRCRackID" in col_map and len(meta_row) > col_map["SRCRackID"]:
                    metadata["rack_id"] = meta_row[col_map["SRCRackID"]]
                else:
                    metadata["rack_id"] = "Unknown"
                    
                if "SRCRack" in col_map and len(meta_row) > col_map["SRCRack"]:
                    metadata["rack_type"] = meta_row[col_map["SRCRack"]]
                
                # Parse operations from row 3 onwards
                has_operations = False
                min_pos = 999
                
                for i in range(2, len(rows)):
                    row = rows[i]
                    if not row: continue
                    
                    try:
                        # Get Position (Target Well)
                        if "Position" in col_map and len(row) > col_map["Position"] and row[col_map["Position"]]:
                            pos_str = row[col_map["Position"]]
                            if not pos_str.isdigit(): continue
                            pos = int(pos_str)
                        else:
                            continue
                            
                        # Get Volume
                        vol = 0.0
                        if "Volume" in col_map and len(row) > col_map["Volume"] and row[col_map["Volume"]]:
                            vol = float(row[col_map["Volume"]])
                            
                        # Get Error
                        error = 0
                        if "Error" in col_map and len(row) > col_map["Error"] and row[col_map["Error"]]:
                            error = int(row[col_map["Error"]])
                            
                        # Get Source Info
                        src_pos = ""
                        if "SRCPos" in col_map and len(row) > col_map["SRCPos"]:
                            src_pos = row[col_map["SRCPos"]]
                            
                        src_id = ""
                        if "SRCTubeID" in col_map and len(row) > col_map["SRCTubeID"]:
                            src_id = row[col_map["SRCTubeID"]]
                            
                        # Store data if volume > 0 (meaning an operation occurred)
                        if vol > 0:
                            has_operations = True
                            if pos < min_pos: min_pos = pos
                            
                            well_data[pos] = {
                                "volume": vol,
                                "error": error,
                                "src_pos": src_pos,
                                "src_id": src_id,
                                "timestamp": row[col_map["Time"]] if "Time" in col_map and len(row) > col_map["Time"] else ""
                            }
                            
                            # Track source usage
                            if src_pos:
                                try:
                                    src_idx = int(src_pos)
                                    if src_idx not in source_usage:
                                        source_usage[src_idx] = {"error": 0, "targets": []}
                                    
                                    if error != 0:
                                        source_usage[src_idx]["error"] = error
                                    source_usage[src_idx]["targets"].append(pos)
                                except ValueError:
                                    pass
                            
                    except ValueError:
                        continue
                        
                if not has_operations:
                    return None
                
                metadata["min_pos"] = min_pos
                return {"metadata": metadata, "wells": well_data, "source_usage": source_usage}
                
        except Exception as e:
            print(f"Error parsing {filepath}: {e}")
            return None

    @staticmethod
    def scan_directory(directory, max_age_minutes=None):
        """
        Scans a directory for relevant CSV files.
        """
        results = []
        global_source_usage = set()
        
        dir_path = pathlib.Path(directory)
        
        if not dir_path.exists():
            return results, global_source_usage
            
        now = datetime.datetime.now()
        
        for file_path in dir_path.glob("*.CSV"):
            if max_age_minutes is not None:
                mtime = datetime.datetime.fromtimestamp(file_path.stat().st_mtime)
                if (now - mtime).total_seconds() > (max_age_minutes * 60):
                    continue
            
            data = LogParser.parse_file(file_path)
            if data:
                data["filename"] = file_path.name
                results.append(data)
                # Collect all source positions used
                for src_pos in data["source_usage"].keys():
                    global_source_usage.add(src_pos)
                
        return results, global_source_usage

class PulsingPlateWidget(WellPlateWidget):
    def __init__(self, title, parent=None):
        super().__init__(fixed_size=False, show_title=False, parent=parent)
        self.plate_title = title
        self.pulsing_wells = set() # Set of indices to pulse
        self.pulse_phase = 0.0
        self.pulse_timer = QTimer(self)
        self.pulse_timer.timeout.connect(self._update_pulse)
        self.pulse_timer.start(50) # 20 FPS
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        if self.cols == 0: return 0
        # Margins: Left=5, Right=5, Top=35, Bottom=5 -> Total W=10, H=40
        # We want square cells: cell_h = cell_w
        # cell_w = (width - 10) / cols
        # height = (cell_w * rows) + 40
        return int(((width - 10) / self.cols) * self.rows + 40)

    def _update_pulse(self):
        if not self.pulsing_wells:
            return
        self.pulse_phase += 0.1
        if self.pulse_phase > math.pi * 2:
            self.pulse_phase -= math.pi * 2
        self.update()
        
    def set_pulsing(self, wells):
        self.pulsing_wells = set(wells) if wells else set()
        self.update()

    def draw_plate_frame(self, painter):
        # Draw the plate frame
        frame_rect = self.rect().adjusted(5, 35, -5, -5)
        
        # Draw title
        painter.setFont(QFont("Arial", 14, QFont.Bold))
        painter.setPen(QColor("#e0e0e0"))
        title_rect = self.rect().adjusted(5, 5, -5, -self.height() + 30)
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.plate_title)
        
        # Draw frame background using frame_color
        frame_color = QColor(self.frame_color)
        painter.fillRect(frame_rect, frame_color.lighter(130))
        painter.setPen(QPen(frame_color, 3))
        painter.drawRect(frame_rect)
        
        return 35, self.width(), self.height() # top_margin, width, height

    def draw_well(self, painter, rect, well_index, color_fill, color_outline, text_color=None):
        # Handle pulsing
        if well_index in self.pulsing_wells:
            # Orange outline with pulsing width/opacity
            pulse_val = (math.sin(self.pulse_phase) + 1) / 2 # 0.0 to 1.0
            width = 3 + (pulse_val * 3) # 3 to 6
            alpha = 150 + (pulse_val * 105) # 150 to 255
            
            pulse_color = QColor("#ff8c00") # Orange
            pulse_color.setAlpha(int(alpha))
            
            painter.setPen(QPen(pulse_color, width))
            painter.setBrush(QBrush(color_fill))
        else:
            painter.setPen(QPen(color_outline, 1))
            painter.setBrush(QBrush(color_fill))
            
        if self.shape == 'circle':
            # Enforce square aspect ratio for circles to avoid ovals
            side = min(rect.width(), rect.height())
            center = rect.center()
            circle_rect = QRect(0, 0, side, side)
            circle_rect.moveCenter(center)
            painter.drawEllipse(circle_rect)
        else:
            painter.drawRect(rect)
            
        # Draw coordinate
        well_name = self.index_to_coord(well_index)
        
        painter.setFont(QFont("Arial", 9))
        if text_color:
            painter.setPen(QPen(text_color))
        elif color_fill.lightness() < 128:
            painter.setPen(QPen(QColor("#FFFFFF")))
        else:
            painter.setPen(QPen(QColor("#000000")))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, well_name)

class AnalysisPlateWidget(PulsingPlateWidget):
    def __init__(self, title, well_data, min_pos, disabled_wells=None, parent=None):
        super().__init__(title, parent)
        self.well_data = well_data
        self.min_pos = min_pos
        self.disabled_wells = disabled_wells if disabled_wells else []
        self.setMinimumSize(240, 180)
        # Removed setMaximumSize to allow vertical scaling
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        top_margin, widget_width, widget_height = self.draw_plate_frame(painter)
        
        cell_width = (widget_width - 10) / self.cols
        cell_height = (widget_height - top_margin - 10) / self.rows
        
        for row in range(self.rows):
            for col in range(self.cols):
                well_index = (col * self.rows) + row + 1
                
                color_fill = QColor("#ffffff") # Default empty (White)
                color_outline = QColor("#cccccc")
                
                if well_index in self.disabled_wells:
                    color_fill = QColor("#e0e0e0") # Disabled (Light Gray)
                elif well_index in self.well_data:
                    data = self.well_data[well_index]
                    if data["error"] != 0:
                        color_fill = QColor("#cf3838") # Red for error
                    else:
                        color_fill = QColor("#00b347") # Green for success
                elif well_index < self.min_pos:
                    color_fill = QColor("#ffd700") # Yellow for previously filled
                
                rect = QRect(5 + col * cell_width, top_margin + row * cell_height, cell_width - 2, cell_height - 2)
                self.draw_well(painter, rect, well_index, color_fill, color_outline)

class SourcePlateWidget(PulsingPlateWidget):
    def __init__(self, title, parent=None):
        super().__init__(title, parent)
        self.current_source_usage = {}
        self.global_source_usage = set()
        self.shape = 'circle' # Force circle shape for origin
        self.setMinimumSize(240, 180)
        # Removed setMaximumSize to allow vertical scaling
        
    def set_dimensions(self, rows, cols):
        super().set_dimensions(rows, cols)
        self.updateGeometry()
        
    def set_data(self, current_usage, global_usage):
        self.current_source_usage = current_usage
        self.global_source_usage = global_usage
        self.update()
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        top_margin, widget_width, widget_height = self.draw_plate_frame(painter)
        
        cell_width = (widget_width - 10) / self.cols
        cell_height = (widget_height - top_margin - 10) / self.rows
        
        for row in range(self.rows):
            for col in range(self.cols):
                well_index = (col * self.rows) + row + 1
                
                color_fill = QColor("#505050") # Default empty
                color_outline = QColor("#303030")
                
                if well_index in self.current_source_usage:
                    # Used in current box
                    if self.current_source_usage[well_index]["error"] != 0:
                        color_fill = QColor("#cf3838") # Red
                    else:
                        color_fill = QColor("#00b347") # Green
                elif well_index in self.global_source_usage:
                    # Used in other boxes
                    color_fill = QColor("#808080") # Gray
                else:
                    # Not used at all - keep default dark gray
                    pass
                
                rect = QRect(5 + col * cell_width, top_margin + row * cell_height, cell_width - 2, cell_height - 2)
                self.draw_well(painter, rect, well_index, color_fill, color_outline)

class DetailView(QWidget):
    back_clicked = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        
        # Top bar with back button
        top_bar = QHBoxLayout()
        self.back_btn = QPushButton("← Tilbake")
        self.back_btn.setFixedSize(200, 60)
        self.back_btn.setFont(QFont("Arial", 16, QFont.Bold))
        self.back_btn.clicked.connect(self.back_clicked.emit)
        top_bar.addWidget(self.back_btn)
        top_bar.addStretch()
        self.layout.addLayout(top_bar)
        
        # Scroll Area for vertical stacking
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background-color: transparent; border: none;")
        
        content_widget = QWidget()
        self.content_layout = QVBoxLayout(content_widget)
        self.content_layout.setSpacing(20)
        
        # Target Plate (Top)
        self.target_plate = None # Created dynamically
        
        # Source Plate (Middle)
        self.source_plate = SourcePlateWidget("Kilde (Origin)")
        self.source_plate.set_interactive(True)
        self.source_plate.well_clicked.connect(self.on_source_clicked)
        self.source_plate.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.source_plate.setMinimumHeight(400) # Make it big
        
        # Info Text (Bottom)
        self.info_label = QLabel()
        self.info_label.setFont(QFont("Arial", 16))
        self.info_label.setAlignment(Qt.AlignCenter)
        self.info_label.setWordWrap(True)
        self.info_label.setStyleSheet("color: #e0e0e0; padding: 20px; background-color: #333; border-radius: 8px;")
        
        self.content_layout.addWidget(self.info_label) # Placeholder position
        self.content_layout.addWidget(self.source_plate) # Placeholder position
        
        scroll.setWidget(content_widget)
        self.layout.addWidget(scroll)
        
    def set_data(self, data, global_source_usage, source_rows=8, source_cols=12):
        self.data = data
        
        # Clear previous target plate
        if self.target_plate:
            self.content_layout.removeWidget(self.target_plate)
            self.target_plate.deleteLater()
            
        # Get group info for styling
        group_info = data.get('group_info', {})
        frame_color = group_info.get('color', '#808080')
        shape = group_info.get('shape', 'rect')
        disabled_wells = group_info.get('disabledWells', [])
            
        # Create new target plate
        title = f"Mål: {data['metadata']['rack_id']} ({data['filename']})"
        self.target_plate = AnalysisPlateWidget(title, data['wells'], data['metadata']['min_pos'], disabled_wells)
        self.target_plate.frame_color = frame_color
        self.target_plate.shape = shape
        self.target_plate.set_interactive(True)
        self.target_plate.well_clicked.connect(self.on_target_clicked)
        self.target_plate.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding) # Allow expansion
        self.target_plate.setMinimumHeight(400) # Make it big
        
        # Insert at top
        self.content_layout.insertWidget(0, self.target_plate)
        
        # Setup Source Plate
        self.source_plate.set_dimensions(source_rows, source_cols)
        self.source_plate.set_data(data['source_usage'], global_source_usage)
        self.source_plate.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding) # Allow expansion
        
        # Reset selection
        self.target_plate.set_pulsing(None)
        self.source_plate.set_pulsing(None)
        self.info_label.setText("Klikk på en brønn i målplaten eller kildeplaten for å se koblingen.")
        
    def on_target_clicked(self, well_index):
        # Highlight target
        self.target_plate.set_pulsing([well_index])
        
        # Find source
        src_indices = []
        src_text = "Ingen kilde"
        
        if well_index in self.data['wells']:
            well_info = self.data['wells'][well_index]
            src_pos_str = well_info['src_pos']
            if src_pos_str and src_pos_str.isdigit():
                src_idx = int(src_pos_str)
                src_indices.append(src_idx)
                src_text = f"Kilde: {self.source_plate.index_to_coord(src_idx)}"
            
            # Update Info
            target_text = f"Mål: {self.target_plate.index_to_coord(well_index)}"
            status = "OK" if well_info['error'] == 0 else f"FEIL ({well_info['error']})"
            self.info_label.setText(f"{src_text} -> {target_text}\nStatus: {status}\nVolum: {well_info['volume']} µl")
        else:
            self.info_label.setText(f"Mål: {self.target_plate.index_to_coord(well_index)}\nIngen data.")
            
        self.source_plate.set_pulsing(src_indices)
        
    def on_source_clicked(self, well_index):
        # Highlight source
        self.source_plate.set_pulsing([well_index])
        
        # Find targets
        target_indices = []
        if well_index in self.data['source_usage']:
            target_indices = self.data['source_usage'][well_index]['targets']
            targets_str = ", ".join([self.target_plate.index_to_coord(t) for t in target_indices])
            src_text = f"Kilde: {self.source_plate.index_to_coord(well_index)}"
            self.info_label.setText(f"{src_text} -> Mål: {targets_str}")
        else:
            self.info_label.setText(f"Kilde: {self.source_plate.index_to_coord(well_index)}\nIngen mål i denne boksen.")
            
        self.target_plate.set_pulsing(target_indices)

class PostAnalysisWindow(QMainWindow):
    def __init__(self, script_config=None):
        super().__init__()
        self.script_config = script_config
        self.setWindowTitle("Post-Pipettering Kvalitetskontroll")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        
        # Apply dark theme
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #2b2b2b;
                color: #e0e0e0;
            }
            QLabel {
                color: #e0e0e0;
            }
            QScrollArea {
                border: none;
                background-color: #2b2b2b;
            }
            QPushButton {
                background-color: #3d3d3d;
                color: #e0e0e0;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 8px;
            }
            QPushButton:hover {
                background-color: #4d4d4d;
                border: 1px solid #777777;
            }
        """)
        
        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)
        
        # Overview Screen
        self.overview_widget = QWidget()
        self.overview_layout = QVBoxLayout(self.overview_widget)
        
        # Header
        header_layout = QVBoxLayout()
        self.header_title = QLabel("Pipettering fullført")
        self.header_title.setFont(QFont("Arial", 32, QFont.Bold))
        self.header_title.setAlignment(Qt.AlignCenter)
        subtitle = QLabel("Kontroller boks/plate ved å trykke på den. Trykk deretter på en brønn/et rør for å se opphav eller mål")
        subtitle.setFont(QFont("Arial", 14))
        subtitle.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(self.header_title)
        header_layout.addWidget(subtitle)
        self.overview_layout.addLayout(header_layout)
        
        # Top bar controls
        top_bar = QHBoxLayout()
        self.settings_btn = QPushButton("📂")
        self.settings_btn.setFixedSize(50, 50)
        self.settings_btn.setFont(QFont("Arial", 20))
        self.settings_btn.setToolTip("Velg rapportmappe")
        self.settings_btn.clicked.connect(self.change_directory)
        
        self.config_btn = QPushButton("⚙️")
        self.config_btn.setFixedSize(50, 50)
        self.config_btn.setFont(QFont("Arial", 20))
        self.config_btn.setToolTip("Last inn script-konfigurasjon")
        self.config_btn.clicked.connect(self.load_script_config)
        
        self.close_btn = QPushButton("X")
        self.close_btn.setFixedSize(50, 50)
        self.close_btn.setStyleSheet("background-color: #c00000; font-weight: bold; font-size: 20px; border-radius: 25px;")
        self.close_btn.clicked.connect(self.close)
        
        top_bar.addWidget(self.settings_btn)
        top_bar.addSpacing(10)
        top_bar.addWidget(self.config_btn)
        top_bar.addStretch()
        top_bar.addWidget(self.close_btn)
        self.overview_layout.addLayout(top_bar)
        
        # Grid for plates
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        self.plates_container = QWidget()
        self.plates_grid = QGridLayout(self.plates_container)
        self.plates_grid.setSpacing(20)
        scroll_area.setWidget(self.plates_container)
        self.overview_layout.addWidget(scroll_area)
        
        # Legend
        legend_layout = QHBoxLayout()
        legend_layout.addStretch()
        self.add_legend_item(legend_layout, "#00b347", "Ingen error")
        self.add_legend_item(legend_layout, "#cf3838", "Clot- eller detection error")
        self.add_legend_item(legend_layout, "#ffd700", "Tidligere fylt")
        legend_layout.addStretch()
        self.overview_layout.addLayout(legend_layout)
        
        # Bottom Button
        finish_btn = QPushButton("KONTROLL FULLFØRT, AVSLUTT")
        finish_btn.setMinimumHeight(100)
        finish_btn.setFont(QFont("Arial", 24, QFont.Bold))
        finish_btn.setStyleSheet("background-color: #0078d4; color: white;")
        finish_btn.clicked.connect(self.close)
        self.overview_layout.addWidget(finish_btn)
        
        # Detail Screen
        self.detail_view = DetailView()
        self.detail_view.back_clicked.connect(self.show_overview)
        
        self.stacked_widget.addWidget(self.overview_widget)
        self.stacked_widget.addWidget(self.detail_view)
        
        # Load settings
        self.load_settings()
        self.load_data()
        
    def add_legend_item(self, layout, color, text):
        item = QWidget()
        l = QHBoxLayout(item)
        l.setContentsMargins(0,0,0,0)
        box = QLabel()
        box.setFixedSize(20, 20)
        box.setStyleSheet(f"background-color: {color}; border: 1px solid #555;")
        label = QLabel(text)
        l.addWidget(box)
        l.addWidget(label)
        layout.addWidget(item)
        layout.addSpacing(20)
        
    def load_settings(self):
        settings_path = current_dir / "settings.json"
        try:
            with open(settings_path, 'r') as f:
                self.settings = json.load(f)
                print(f"Loaded settings from: {settings_path}")
                
            # Auto-load last script config if not already provided
            if not self.script_config and "last_script_config" in self.settings:
                config_path = self.settings["last_script_config"]
                if os.path.exists(config_path):
                    try:
                        with open(config_path, 'r', encoding='utf-8') as f:
                            self.script_config = json.load(f)
                        print(f"Auto-loaded config: {config_path}")
                    except Exception as e:
                        print(f"Failed to auto-load config: {e}")
                else:
                    print(f"Config path not found: {config_path}")
                        
        except FileNotFoundError:
            print(f"Settings file not found at: {settings_path}")
            self.settings = {"reports_dir": "test_reports/standard"}
            
    def save_settings(self):
        settings_path = current_dir / "settings.json"
        try:
            with open(settings_path, 'w') as f:
                json.dump(self.settings, f, indent=4)
        except Exception as e:
            print(f"Failed to save settings: {e}")
            
    def change_directory(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Velg rapportmappe", self.settings.get("reports_dir", "."))
        if dir_path:
            self.settings["reports_dir"] = dir_path
            self.save_settings()
            self.load_data()
            
    def load_script_config(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Velg script-konfigurasjon", self.settings.get("reports_dir", "."), "JSON Files (*.json)")
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    self.script_config = json.load(f)
                QMessageBox.information(self, "Suksess", f"Lastet konfigurasjon for: {self.script_config.get('scriptName', 'Ukjent')}")
                self.load_data()
            except Exception as e:
                QMessageBox.critical(self, "Feil", f"Kunne ikke laste konfigurasjon:\n{e}")
        
    def load_data(self):
        # Clear existing
        while self.plates_grid.count():
            item = self.plates_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        reports_dir = self.settings.get("reports_dir", "test_reports/standard")
        all_results, self.global_source_usage = LogParser.scan_directory(reports_dir, max_age_minutes=None)
        
        if not all_results:
            self.plates_grid.addWidget(QLabel("Ingen rapporter funnet i mappen."), 0, 0)
            return

        row = 0
        col = 0
        max_cols = 3 # More columns since groups are vertical stacks
        
        if self.script_config:
            script_name = self.script_config.get("scriptName", "Ukjent Script")
            print(f"Filtering results for script: {script_name}")
            self.setWindowTitle(f"Post-Pipettering Kvalitetskontroll - {script_name}")
            self.header_title.setText(f"Resultater: {script_name}")
            
            # Iterate through configured groups
            for group in self.script_config.get("boxGroups", []):
                labware_name = group.get("labwareName", "")
                if not labware_name:
                    continue
                
                # Find matching files for this group
                group_results = []
                for data in all_results:
                    if labware_name.lower() in data['filename'].lower():
                        data['group_info'] = group
                        group_results.append(data)
                
                # Create Box Group Widget
                group_widget = PostAnalysisBoxGroupWidget(group, group_results)
                group_widget.plate_clicked.connect(self.show_detail)
                
                self.plates_grid.addWidget(group_widget, row, col)
                col += 1
                if col >= max_cols:
                    col = 0
                    row += 1
                    
        else:
            self.setWindowTitle("Post-Pipettering Kvalitetskontroll")
            self.header_title.setText("Alle rapporter (Ingen script valgt)")
            
            # Fallback: Show all files as individual items (or grouped by something else?)
            # For now, just dump them in a generic group
            generic_group = {"groupName": "Alle Rapporter", "color": "#808080", "shape": "rect"}
            group_widget = PostAnalysisBoxGroupWidget(generic_group, all_results)
            group_widget.plate_clicked.connect(self.show_detail)
            self.plates_grid.addWidget(group_widget, 0, 0)
                
    def show_detail(self, data):
        source_rows = 8
        source_cols = 12
        
        if self.script_config and "sourceLayout" in self.script_config:
            layout_str = self.script_config["sourceLayout"]
            if "x" in layout_str:
                try:
                    parts = layout_str.split("x")
                    source_rows = int(parts[0])
                    source_cols = int(parts[1])
                except ValueError:
                    pass # Keep default
                    
        self.detail_view.set_data(data, self.global_source_usage, source_rows, source_cols)
        self.stacked_widget.setCurrentWidget(self.detail_view)
        
    def show_overview(self):
        self.stacked_widget.setCurrentWidget(self.overview_widget)

class PostAnalysisBoxGroupWidget(QFrame):
    plate_clicked = Signal(object) # Emits data object

    def __init__(self, group_data, results, parent=None):
        super().__init__(parent)
        self.group_data = group_data
        self.results = results
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        # Style like BoxGroupWidget (mimicking gui_screens.py)
        self.setStyleSheet("""
            PostAnalysisBoxGroupWidget {
                background-color: #f0f0f0;
                border: 1px solid #ccc;
                border-radius: 8px;
            }
        """)
        
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(8, 8, 8, 8)
        
        # Title
        name_label = QLabel(self.group_data.get("groupName", "Boksgruppe"))
        name_label.setFont(QFont("Arial", 22, QFont.Bold))
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setStyleSheet("color: black; border: none;")
        name_label.setWordWrap(True)
        main_layout.addWidget(name_label)
        
        # Plates Container
        self.plates_container = QWidget()
        self.plates_container.setStyleSheet("background-color: transparent; border: none;")
        self.plates_layout = QVBoxLayout(self.plates_container)
        self.plates_layout.setContentsMargins(5, 5, 5, 5)
        self.plates_layout.setSpacing(15) # Space between plates
        
        main_layout.addWidget(self.plates_container, stretch=1)
        
        self._add_plates()

    def _add_plates(self):
        frame_color = self.group_data.get("color", "#808080")
        shape = self.group_data.get("shape", "rect")
        
        if not self.results:
            lbl = QLabel("Ingen data funnet")
            lbl.setStyleSheet("color: #555; font-style: italic; border: none;")
            lbl.setAlignment(Qt.AlignCenter)
            self.plates_layout.addWidget(lbl)
            return

        # Sort results by filename (assuming chronological or sequential naming)
        sorted_results = sorted(self.results, key=lambda x: x['filename'])

        for i, data in enumerate(sorted_results):
            # Container for plate + button
            plate_container = QWidget()
            plate_layout = QVBoxLayout(plate_container)
            plate_layout.setContentsMargins(0, 0, 0, 0)
            plate_layout.setSpacing(5)
            
            # Plate Title (Rack ID)
            rack_id = data['metadata'].get('rack_id', f"Plate {i+1}")
            
            # Create AnalysisPlateWidget
            # We use fixed_size=False to let it scale like in BoxGroupWidget
            disabled_wells = self.group_data.get("disabledWells", [])
            plate = AnalysisPlateWidget(rack_id, data['wells'], data['metadata']['min_pos'], disabled_wells)
            plate.shape = shape
            plate.frame_color = frame_color
            plate.setMinimumSize(240, 160)
            plate.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            
            # Make it look like the main app
            plate.set_interactive(False) # Not interactive in overview
            
            plate_layout.addWidget(plate)
            
            # Action Button
            btn = QPushButton("🔍 Se Detaljer / Feil")
            btn.setFont(QFont("Arial", 12, QFont.Bold))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {frame_color};
                    color: white;
                    border: none;
                    padding: 8px;
                    border-radius: 4px;
                }}
                QPushButton:hover {{
                    background-color: #333;
                }}
            """)
            btn.clicked.connect(lambda checked, d=data: self.plate_clicked.emit(d))
            plate_layout.addWidget(btn)
            
            self.plates_layout.addWidget(plate_container)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PostAnalysisWindow()
    
    # Monitor selection logic (same as main.py)
    screens = app.screens()
    monitor_index = 1
    if monitor_index < len(screens):
        target_screen = screens[monitor_index]
        window.setGeometry(target_screen.geometry())
        
    window.showFullScreen()
    window.activateWindow()
    window.raise_()
    
    sys.exit(app.exec())
