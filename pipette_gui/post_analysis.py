import sys
import os
import csv
import pathlib
import datetime
import json
import math
from typing import Optional
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QLabel, QScrollArea, QGridLayout, 
                               QFrame, QMessageBox, QPushButton, QStackedWidget,
                               QSizePolicy, QFileDialog, QScroller)
from PySide6.QtCore import Qt, QSize, QRect, Signal, QTimer
from PySide6.QtGui import QPainter, QColor, QBrush, QPen, QFont, QPixmap

# Add the parent directory to sys.path to import gui_widgets
current_dir = pathlib.Path(__file__).resolve().parent
sys.path.append(str(current_dir))

from gui_widgets import WellPlateWidget

# ERROR CODE MAPPING
# Add error code descriptions here. Format: error_code_number: "Description text"
# To add a new error code, copy a line below and modify the number and description.
# (THE FOLLOWING ERROR CODES ARE SPECIFIC TO TECAN EVOWARE 2)
ERROR_CODE_DESCRIPTIONS = {
    4194305: "Liquid detection error - pipetted air instead of liquid",
    524292: "Clot error - continied with clot",
    1048580: "Clot error - ignored clot error",
    # Add more error codes here following the same format:
    # 3: "Your error description",
}

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
                
                # Extract GridPos and SiteOnGrid for layout positioning
                if "GridPos" in col_map and len(meta_row) > col_map["GridPos"]:
                    try:
                        metadata["grid_pos"] = int(meta_row[col_map["GridPos"]])
                    except (ValueError, IndexError):
                        metadata["grid_pos"] = None
                else:
                    metadata["grid_pos"] = None
                    
                if "SiteOnGrid" in col_map and len(meta_row) > col_map["SiteOnGrid"]:
                    try:
                        metadata["site_on_grid"] = int(meta_row[col_map["SiteOnGrid"]])
                    except (ValueError, IndexError):
                        metadata["site_on_grid"] = None
                else:
                    metadata["site_on_grid"] = None
                
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
                            
                            # Handle pooled samples - check if position already exists
                            if pos in well_data:
                                # Pooled sample - append to src_pos list
                                existing_src = well_data[pos]["src_pos"]
                                if isinstance(existing_src, list):
                                    if src_pos and src_pos not in existing_src:
                                        existing_src.append(src_pos)
                                else:
                                    # Convert single value to list
                                    well_data[pos]["src_pos"] = [existing_src, src_pos] if src_pos and src_pos != existing_src else [existing_src]
                                # Update volume (cumulative)
                                well_data[pos]["volume"] += vol
                                # Keep highest error code
                                if error > well_data[pos]["error"]:
                                    well_data[pos]["error"] = error
                            else:
                                # New position
                                well_data[pos] = {
                                    "volume": vol,
                                    "error": error,
                                    "src_pos": [src_pos] if src_pos else [],
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
                                    if pos not in source_usage[src_idx]["targets"]:
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
        self.pulse_timer.start(30) # Enhanced: 30ms for smoother animation (~33 FPS)
        # WellPlateWidget(fixed_size=False) sets a restrictive max size (520x380).
        # For PA we want these widgets to scale freely.
        # Qt's practical "infinite" widget size. Using the literal avoids import issues.
        self.setMaximumSize(16777215, 16777215)
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
        self.pulse_phase += 0.15  # Slightly faster animation
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
        title_color = getattr(self, "title_text_color", None)
        if title_color is None:
            # Choose a contrasting title color based on the widget background.
            # (Overview cards can have a light background; detail view is dark.)
            bg = self.palette().window().color()
            title_color = Qt.GlobalColor.black if bg.lightness() > 128 else QColor("#e0e0e0")
        painter.setPen(title_color)
        title_rect = self.rect().adjusted(5, 5, -5, -self.height() + 30)
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.plate_title)
        
        # Draw frame background using frame_color
        frame_color = QColor(self.frame_color)
        painter.fillRect(frame_rect, frame_color.lighter(130))
        painter.setPen(QPen(frame_color, 3))
        painter.drawRect(frame_rect)
        
        return 35, self.width(), self.height() # top_margin, width, height

    def draw_well(self, painter, rect, well_index, color_fill, color_outline, text_color=None):
        # Handle pulsing with rainbow colors
        if well_index in self.pulsing_wells:
            # Enhanced: Rainbow colors using HSV color space
            pulse_val = (math.sin(self.pulse_phase) + 1) / 2 # 0.0 to 1.0
            
            # Rainbow hue cycling based on pulse phase
            hue = int((self.pulse_phase / (math.pi * 2)) * 360) % 360
            saturation = 255
            value = 255
            
            pulse_color = QColor.fromHsv(hue, saturation, value)
            
            # Enhanced: Wider width range (2-8px instead of 3-6px)
            width = 2 + (pulse_val * 6) # 2 to 8
            alpha = 180 + (pulse_val * 75) # 180 to 255 for better visibility
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


class AspectRatioContainer(QWidget):
    """Keeps a single child widget at a fixed aspect ratio, letterboxed and centered."""

    def __init__(self, child: QWidget, aspect_w: float, aspect_h: float, parent=None):
        super().__init__(parent)
        self._child = child
        self._ratio = (aspect_w / aspect_h) if aspect_h else 1.0  # width / height
        self._child.setParent(self)
        self._child.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def resizeEvent(self, event):
        w = max(0, self.width())
        h = max(0, self.height())
        if w == 0 or h == 0:
            return

        # Prefer full width, then clamp by available height.
        target_w = w
        target_h = int(round(target_w / self._ratio)) if self._ratio else h
        if target_h > h:
            target_h = h
            target_w = int(round(target_h * self._ratio)) if self._ratio else w

        x = int((w - target_w) / 2)
        y = int((h - target_h) / 2)
        self._child.setGeometry(x, y, target_w, target_h)
        super().resizeEvent(event)

class SourcePlateWidget(PulsingPlateWidget):
    def __init__(self, title, parent=None):
        super().__init__(title, parent)
        self.current_source_usage = {}
        self.global_source_usage = set()
        self.shape = 'circle' # Force circle shape for origin
        self.source_layout_type = "6x16"  # Default
        
    def set_dimensions(self, rows, cols):
        super().set_dimensions(rows, cols)
        # Detect layout type for coordinate system
        if rows == 16 and cols == 6:
            self.source_layout_type = "6x16"
        else:
            self.source_layout_type = f"{cols}x{rows}"
        self.updateGeometry()
    
    def sizeHint(self):
        # Return large size hint to encourage expansion
        return QSize(400, 800)
    
    def minimumSizeHint(self):
        # Return minimal size
        return QSize(200, 400)
    
    def index_to_coord(self, index):
        """
        Override to handle 6x16 coordinate system.
        For 6x16: columns are 1-6 (numeric), rows are A-P (alphabetic)
        Index 1 = A1 (top-left), Index 2 = B1, ..., Index 16 = P1, Index 17 = A2, etc.
        Formula: column = (index-1) // 16 + 1, row = chr(65 + (index-1) % 16)
        """
        if self.source_layout_type == "6x16":
            # 6 columns (numeric 1-6), 16 rows (alphabetic A-P)
            col_num = ((index - 1) // 16) + 1
            row_letter = chr(65 + ((index - 1) % 16))
            return f"{row_letter}{col_num}"
        else:
            # Default behavior: alphabetic rows, numeric columns
            return super().index_to_coord(index)
        
    def set_data(self, current_usage, global_usage):
        self.current_source_usage = current_usage
        self.global_source_usage = global_usage
        self.update()
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw title
        painter.setFont(QFont("Arial", 14, QFont.Bold))
        painter.setPen(QColor("#e0e0e0"))
        title_rect = QRect(5, 5, self.width() - 10, 30)
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.plate_title)
        
        top_margin = 35
        available_width = self.width() - 10
        available_height = self.height() - top_margin - 5
        
        # Fill vertical space first, but clamp by width so we never overflow horizontally.
        cell_size_by_height = (available_height / self.rows) if self.rows else 0
        cell_size_by_width = (available_width / self.cols) if self.cols else 0
        cell_size = min(cell_size_by_height, cell_size_by_width)
        
        # Calculate actual grid dimensions
        grid_width = cell_size * self.cols
        grid_height = cell_size * self.rows
        
        # Center the grid horizontally
        x_offset = 5 + (available_width - grid_width) / 2
        y_offset = top_margin
        
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
                
                # Calculate circle position (edge to edge)
                x = x_offset + col * cell_size
                y = y_offset + row * cell_size
                
                # Create square rect for circle to maintain perfect circular shape
                circle_rect = QRect(int(x), int(y), int(cell_size), int(cell_size))
                
                # Draw well with custom logic for circular shape
                self._draw_circular_well(painter, circle_rect, well_index, color_fill, color_outline)

    def mousePressEvent(self, event):
        # Custom hit testing: the origin grid is centered and may be letterboxed.
        if not self.is_interactive:
            return

        top_margin = 35
        available_width = self.width() - 10
        available_height = self.height() - top_margin - 5
        if self.rows <= 0 or self.cols <= 0 or available_width <= 0 or available_height <= 0:
            return

        cell_size_by_height = available_height / self.rows
        cell_size_by_width = available_width / self.cols
        cell_size = min(cell_size_by_height, cell_size_by_width)
        if cell_size <= 0:
            return

        grid_width = cell_size * self.cols
        x_offset = 5 + (available_width - grid_width) / 2
        y_offset = top_margin

        pos = event.position()
        col = int((pos.x() - x_offset) / cell_size)
        row = int((pos.y() - y_offset) / cell_size)
        if 0 <= col < self.cols and 0 <= row < self.rows:
            well_index = (col * self.rows) + row + 1
            self.well_clicked.emit(well_index)
    
    def _draw_circular_well(self, painter, rect, well_index, color_fill, color_outline):
        """Draw a circular well edge-to-edge with highlighting support"""
        # Handle pulsing with rainbow colors
        if well_index in self.pulsing_wells:
            pulse_val = (math.sin(self.pulse_phase) + 1) / 2
            hue = int((self.pulse_phase / (math.pi * 2)) * 360) % 360
            pulse_color = QColor.fromHsv(hue, 255, 255)
            width = 2 + (pulse_val * 6)
            alpha = 180 + (pulse_val * 75)
            pulse_color.setAlpha(int(alpha))
            painter.setPen(QPen(pulse_color, width))
            painter.setBrush(QBrush(color_fill))
        else:
            painter.setPen(QPen(color_outline, 1))
            painter.setBrush(QBrush(color_fill))
        
        # Draw circle
        painter.drawEllipse(rect)
        
        # Draw coordinate text
        well_name = self.index_to_coord(well_index)
        painter.setFont(QFont("Arial", 8))
        if color_fill.lightness() < 128:
            painter.setPen(QPen(QColor("#FFFFFF")))
        else:
            painter.setPen(QPen(QColor("#000000")))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, well_name)

class DetailView(QWidget):
    back_clicked = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        
        # Top bar with back button
        top_bar = QHBoxLayout()
        self.back_btn = QPushButton("← Tilbake")
        self.back_btn.setFixedSize(200, 60)
        self.back_btn.setFont(QFont("Arial", 16, QFont.Bold))
        self.back_btn.clicked.connect(self.back_clicked.emit)
        top_bar.addWidget(self.back_btn)
        top_bar.addStretch()
        self.layout.addLayout(top_bar)
        
        # Content layout directly in main layout (no scroll area to allow proper expansion)
        # Target Plate (Top) - will be added dynamically
        self.target_plate = None
        
        # Info Text (Middle) - Fixed size
        self.info_label = QLabel()
        self.info_label.setFont(QFont("Arial", 14))
        self.info_label.setAlignment(Qt.AlignCenter)
        self.info_label.setWordWrap(True)
        self.info_label.setStyleSheet("color: #e0e0e0; padding: 10px; background-color: #333; border-radius: 8px;")
        self.info_label.setFixedHeight(80)
        self.info_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.info_label.setAlignment(Qt.AlignCenter)
        
        # Source Plate (Bottom) - will expand to fill remaining vertical space
        self.source_plate = SourcePlateWidget("Kilde (Origin)")
        self.source_plate.set_interactive(True)
        self.source_plate.well_clicked.connect(self.on_source_clicked)
        self.source_plate.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        # Add widgets directly to main layout - target and info are fixed size, source expands
        # Center widgets horizontally by adding them with center alignment
        self.layout.addWidget(self.info_label, 0, Qt.AlignmentFlag.AlignHCenter)  # Placeholder position
        self.layout.addWidget(self.source_plate, 1)  # Expands to fill remaining space
        
    def set_data(self, data, global_source_usage, source_rows=16, source_cols=6):
        self.data = data
        
        # Clear previous target plate
        if self.target_plate:
            self.layout.removeWidget(self.target_plate)
            self.target_plate.deleteLater()
            
        # Get group info for styling
        group_info = data.get('group_info', {})
        frame_color = group_info.get('color', '#808080')
        shape = group_info.get('shape', 'rect')
        disabled_wells = group_info.get('disabledWells', [])
            
        # Create new target plate with fixed size maintaining 12:8 aspect ratio
        title = f"Mål: {data['metadata']['rack_id']} ({data['filename']})"
        self.target_plate = AnalysisPlateWidget(title, data['wells'], data['metadata']['min_pos'], disabled_wells)
        self.target_plate.frame_color = frame_color
        self.target_plate.shape = shape
        self.target_plate.set_interactive(True)
        self.target_plate.well_clicked.connect(self.on_target_clicked)
        
        # Set fixed size with 12:8 aspect ratio (e.g., 600x400 + margins for title)
        plate_width = 720
        plate_height = int(plate_width * (8 / 12)) + 40  # 40px for title
        self.target_plate.setFixedSize(plate_width, plate_height)
        self.target_plate.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        
        # Insert at position 1 (after back button, before info label) with center alignment
        self.layout.insertWidget(1, self.target_plate, 0, Qt.AlignmentFlag.AlignHCenter)
        
        # Setup Source Plate
        self.source_plate.set_dimensions(source_rows, source_cols)
        self.source_plate.set_data(data['source_usage'], global_source_usage)
        self.source_plate.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        # Reset selection
        self.target_plate.set_pulsing(None)
        self.source_plate.set_pulsing(None)
        self.info_label.setText("Klikk på en brønn i målplaten eller kildeplaten for å se koblingen.")
        
    def on_target_clicked(self, well_index):
        # Highlight target
        self.target_plate.set_pulsing([well_index])
        
        # Find source(s) - handle both single and pooled samples
        src_indices = []
        src_text = "Ingen kilde"
        
        if well_index in self.data['wells']:
            well_info = self.data['wells'][well_index]
            src_pos = well_info['src_pos']
            
            # Handle both list (pooled) and legacy single value
            src_pos_list = src_pos if isinstance(src_pos, list) else [src_pos]
            
            for src_pos_str in src_pos_list:
                if src_pos_str and str(src_pos_str).isdigit():
                    src_idx = int(src_pos_str)
                    src_indices.append(src_idx)
            
            if src_indices:
                # Show all source coordinates, comma-separated
                src_coords = ", ".join([self.source_plate.index_to_coord(idx) for idx in src_indices])
                src_text = f"Kilde: {src_coords}"
            
            # Update Info with error description
            target_text = f"Mål: {self.target_plate.index_to_coord(well_index)}"
            error_code = well_info['error']
            if error_code == 0:
                status = "OK"
            else:
                error_desc = ERROR_CODE_DESCRIPTIONS.get(error_code, "Unknown error")
                status = f"FEIL ({error_code}): {error_desc}"
            
            self.info_label.setText(f"{src_text} → {target_text}\nStatus: {status}\nVolum: {well_info['volume']} µl")
        else:
            self.info_label.setText(f"Mål: {self.target_plate.index_to_coord(well_index)}\nIngen data.")
            
        # Highlight all contributing sources
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
            self.info_label.setText(f"{src_text} → Mål: {targets_str}")
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
        
        # Enable touch-friendly kinetic scrolling on overview
        QScroller.grabGesture(scroll_area.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)
        
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

    def _read_text_file_best_effort(self, file_path: pathlib.Path) -> Optional[str]:
        try:
            raw = file_path.read_bytes()
        except Exception:
            return None

        for enc in ("utf-8-sig", "utf-8", "cp1252"):
            try:
                return raw.decode(enc).strip()
            except Exception:
                continue
        return raw.decode("utf-8", errors="replace").strip()

    def _auto_load_script_config_from_selected_script(self):
        """If no config is loaded, infer it from selected_script.txt (robot targetValue)."""
        if self.script_config:
            return

        candidates = [
            pathlib.Path("C:/robot/selected_script.txt"),
            current_dir.parent / "robot" / "selected_script.txt",
        ]
        selected_value = None
        for p in candidates:
            if p.exists():
                selected_value = self._read_text_file_best_effort(p)
                if selected_value:
                    break

        if not selected_value:
            return

        selected_norm = selected_value.strip().lower()
        scripts_dir = current_dir / "scripts"
        if not scripts_dir.exists():
            return

        # Prefer matching by config.json "targetValue" so folder names can differ.
        for script_folder in sorted([d for d in scripts_dir.iterdir() if d.is_dir()]):
            config_path = script_folder / "config.json"
            if not config_path.exists():
                continue
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
            except Exception:
                continue

            target_value = str(cfg.get("targetValue", "")).strip().lower()
            if target_value and target_value == selected_norm:
                self.script_config = cfg
                # Cache for next launch.
                self.settings["last_script_config"] = str(config_path)
                self.save_settings()
                return
        
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

            # If no config is loaded yet, try inferring it from the robot's selected script value.
            self._auto_load_script_config_from_selected_script()
                        
        except FileNotFoundError:
            print(f"Settings file not found at: {settings_path}")
            self.settings = {"reports_dir": "test_reports/standard"}
            self._auto_load_script_config_from_selected_script()
            
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
        # Only process recent .CSV files (default: last 2 minutes).
        # TESTING: comment out the next line and uncomment the one after it.
        max_age_minutes = 2
        # max_age_minutes = None
        all_results, self.global_source_usage = LogParser.scan_directory(reports_dir, max_age_minutes=max_age_minutes)
        
        if not all_results:
            self.plates_grid.addWidget(QLabel("Ingen rapporter funnet i mappen."), 0, 0)
            return
        
        if self.script_config:
            script_name = self.script_config.get("scriptName", "Ukjent Script")
            self.setWindowTitle(f"Post-Pipettering Kvalitetskontroll - {script_name}")
            self.header_title.setText(f"Resultater: {script_name}")

            # No longer filter/exclude by labwareName. We include all eligible reports.
            # Apply styling left-to-right using the script's boxGroups order.
            # Each distinct GridPos column gets the next group style.
            groups = self.script_config.get("boxGroups", []) or []
            style_groups = [g for g in groups if isinstance(g, dict)]

            grid_positions = []
            for d in all_results:
                gp = d.get("metadata", {}).get("grid_pos")
                if isinstance(gp, int):
                    grid_positions.append(gp)
            grid_positions = sorted(set(grid_positions))

            gridpos_to_group = {}
            if style_groups and grid_positions:
                for i, gp in enumerate(grid_positions):
                    gridpos_to_group[gp] = style_groups[i % len(style_groups)]

            for data in all_results:
                gp = data.get("metadata", {}).get("grid_pos")
                if isinstance(gp, int) and gp in gridpos_to_group:
                    data["group_info"] = gridpos_to_group[gp]

            # Lay out each report by physical deck position (same as no-script view)
            gridpos_to_col = {gp: i for i, gp in enumerate(grid_positions)}

            fallback_cols = 2
            flow_index = 0

            for data in sorted(all_results, key=lambda x: (x.get("metadata", {}).get("grid_pos") or 10**9,
                                                          x.get("metadata", {}).get("site_on_grid") or 10**9,
                                                          x.get("filename", ""))):
                meta = data.get("metadata", {})
                gp = meta.get("grid_pos")
                sg = meta.get("site_on_grid")

                if isinstance(gp, int) and gp in gridpos_to_col and isinstance(sg, int):
                    col = gridpos_to_col[gp]
                    row = max(0, sg - 1)
                else:
                    row = flow_index // fallback_cols
                    col = flow_index % fallback_cols
                    flow_index += 1

                card = PostAnalysisPlateCardWidget(data)
                card.plate_clicked.connect(self.show_detail)
                self.plates_grid.addWidget(card, row, col)
                    
        else:
            self.setWindowTitle("Post-Pipettering Kvalitetskontroll")
            self.header_title.setText("Alle rapporter (Ingen script valgt)")

            # Lay out each report by physical deck position:
            # - Same GridPos => same column
            # - Lower SiteOnGrid => higher on screen
            # Map GridPos values (e.g. 19, 25) to contiguous column indices (0..n-1)
            grid_positions = []
            for d in all_results:
                gp = d.get("metadata", {}).get("grid_pos")
                if isinstance(gp, int):
                    grid_positions.append(gp)
            grid_positions = sorted(set(grid_positions))
            gridpos_to_col = {gp: i for i, gp in enumerate(grid_positions)}

            # If GridPos/SiteOnGrid are missing, fall back to a simple flowing layout.
            fallback_cols = 2
            flow_index = 0

            for data in sorted(all_results, key=lambda x: (x.get("metadata", {}).get("grid_pos") or 10**9,
                                                          x.get("metadata", {}).get("site_on_grid") or 10**9,
                                                          x.get("filename", ""))):
                meta = data.get("metadata", {})
                gp = meta.get("grid_pos")
                sg = meta.get("site_on_grid")

                if isinstance(gp, int) and gp in gridpos_to_col and isinstance(sg, int):
                    col = gridpos_to_col[gp]
                    row = max(0, sg - 1)  # SiteOnGrid is 1-based
                else:
                    row = flow_index // fallback_cols
                    col = flow_index % fallback_cols
                    flow_index += 1

                card = PostAnalysisPlateCardWidget(data)
                card.plate_clicked.connect(self.show_detail)
                self.plates_grid.addWidget(card, row, col)
                
    def show_detail(self, data):
        # Default source layout is 6x16 (not 12x8)
        source_rows = 16
        source_cols = 6
        
        if self.script_config and "sourceLayout" in self.script_config:
            layout_str = self.script_config["sourceLayout"]
            if "x" in layout_str:
                try:
                    parts = layout_str.split("x")
                    source_cols = int(parts[0])
                    source_rows = int(parts[1])
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
            disabled_wells = self.group_data.get("disabledWells", [])
            plate = AnalysisPlateWidget(rack_id, data['wells'], data['metadata']['min_pos'], disabled_wells)
            plate.shape = shape
            plate.frame_color = frame_color
            plate.setMinimumSize(240, 160)
            # Overview: keep a locked aspect ratio and force black title text.
            plate.title_text_color = Qt.GlobalColor.black
            plate.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
            
            # Make plate widget itself clickable
            plate.set_interactive(True)
            plate.well_clicked.connect(lambda idx, d=data: self.plate_clicked.emit(d))

            aspect = AspectRatioContainer(plate, aspect_w=12, aspect_h=8)
            plate_layout.addWidget(aspect)
            
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


class PostAnalysisPlateCardWidget(QFrame):
    """Single-report card used in the 'Ingen script valgt' overview."""

    plate_clicked = Signal(object)  # Emits data object

    def __init__(self, data, parent=None):
        super().__init__(parent)
        self.data = data

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setStyleSheet(
            """
            PostAnalysisPlateCardWidget {
                background-color: #f0f0f0;
                border: 1px solid #ccc;
                border-radius: 8px;
            }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        rack_id = self.data.get("metadata", {}).get("rack_id", self.data.get("filename", "Report"))
        group_info = self.data.get("group_info", {}) or {}
        disabled_wells = group_info.get("disabledWells", [])
        shape = group_info.get("shape", "rect")
        frame_color = group_info.get("color", "#808080")

        plate = AnalysisPlateWidget(rack_id, self.data.get("wells", {}), self.data.get("metadata", {}).get("min_pos", 1), disabled_wells)
        plate.shape = shape
        plate.frame_color = frame_color
        plate.set_interactive(True)
        plate.well_clicked.connect(lambda _idx: self.plate_clicked.emit(self.data))
        # Overview: keep a locked aspect ratio and force black title text.
        plate.title_text_color = Qt.GlobalColor.black
        plate.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        layout.addWidget(AspectRatioContainer(plate, aspect_w=12, aspect_h=8))

        btn = QPushButton("🔍 Se Detaljer / Feil")
        btn.setFont(QFont("Arial", 12, QFont.Bold))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            """
            QPushButton {
                background-color: #808080;
                color: white;
                border: none;
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #333;
            }
            """
        )
        btn.clicked.connect(lambda _checked=False: self.plate_clicked.emit(self.data))
        layout.addWidget(btn)

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
