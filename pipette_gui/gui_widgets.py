# Filnavn: gui_widgets.py

from PySide6.QtWidgets import QWidget, QPushButton, QGridLayout, QVBoxLayout, QLabel, QSizePolicy
from PySide6.QtCore import Signal, Qt, QRect, QSize
from PySide6.QtGui import QPainter, QColor, QBrush, QPen, QFont, QPixmap

class ThumbnailButton(QWidget):
    # ... (Denne klassen er uendret)
    clicked = Signal()
    def __init__(self, text, image_path, parent=None):
        super().__init__(parent); self.setMaximumSize(350, 220); self.setMinimumSize(200, 180); main_layout = QVBoxLayout(self); main_layout.setContentsMargins(10, 10, 10, 10); self.image_label = QLabel(); self.image_label.setAlignment(Qt.AlignCenter); self.image_label.setScaledContents(True); pixmap = QPixmap(image_path)
        if pixmap.isNull(): self.image_label.setText("Bilde\nikke funnet")
        else: self.image_label.setPixmap(pixmap)
        self.text_label = QLabel(text); self.text_label.setFont(QFont("Arial", 14, QFont.Bold)); self.text_label.setAlignment(Qt.AlignCenter); self.text_label.setWordWrap(True); main_layout.addWidget(self.image_label, 1); main_layout.addWidget(self.text_label)
        self.setStyleSheet("""ThumbnailButton { background-color: #f0f0f0; border: 1px solid #ccc; border-radius: 8px; } ThumbnailButton:hover { background-color: #aadeff; }""")
    def mousePressEvent(self, event):
        self.clicked.emit(); super().mousePressEvent(event)

class WellPlateWidget(QWidget):
    well_clicked = Signal(int)
    def __init__(self, shape='rect', fixed_size=True, show_title=True, parent=None):
        super().__init__(parent)
        self.rows = 8
        self.cols = 12
        self.start_pos = 1
        self.sample_count = 0
        self.disabled_wells = []
        self.shape = shape
        self.is_interactive = False
        self.temp_selected_well = None
        self.frame_color = "#808080"  # Default gray
        self.row_map = {i: chr(ord('A') + i) for i in range(self.rows)}
        self.show_title = show_title
        if fixed_size:
            self.setFixedSize(520, 380)
        else:
            # For non-fixed size, set minimum size and size policy
            self.setMinimumSize(240, 180)
            self.setMaximumSize(520, 380)
            size_policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            size_policy.setHeightForWidth(True)
            self.setSizePolicy(size_policy)
            
    def sizeHint(self):
        """Suggest optimal size maintaining aspect ratio"""
        # Well plate is 12 cols x 8 rows, so aspect ratio is 3:2
        return QSize(400, 267)  # Reduced from 520x380
        
    def hasHeightForWidth(self):
        """Enable height-for-width layout"""
        return True
        
    def heightForWidth(self, width):
        """Maintain aspect ratio based on width"""
        # Aspect ratio is 12:8 or 3:2
        return int(width * (8 / 12))
    def index_to_coord(self, index):
        if not 1 <= index <= 96: return "?"
        row = (index - 1) % 8; col = (index - 1) // 8
        return f"{chr(ord('A') + row)}{col + 1}"
    def set_state(self, start_pos, sample_count, disabled_wells, frame_color=None):
        self.start_pos = start_pos
        self.sample_count = sample_count
        self.disabled_wells = disabled_wells
        if frame_color:
            self.frame_color = frame_color
        self.update()
    def set_interactive(self, interactive):
        self.is_interactive = interactive
        if not interactive: self.temp_selected_well = None
        self.update()
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw the plate frame
        frame_rect = self.rect().adjusted(10, 45, -10, -10)  # Adjust for margins
        frame_color = QColor(self.frame_color)
        
        # Draw the filled frame background
        painter.fillRect(frame_rect, frame_color.lighter(130))  # Lighter background
        
        # Draw frame border
        painter.setPen(QPen(frame_color, 3))  # Darker border
        painter.drawRect(frame_rect)
        
        if self.show_title:
            painter.setFont(QFont("Arial", 24, QFont.Bold))
            painter.setPen(QColor("#0078d4"))
            coord_text = self.index_to_coord(self.start_pos)
            display_text = f"Startposisjon: {coord_text}"
            bg_rect = self.rect().adjusted(20, 5, -20, -self.height() + 40)
            painter.fillRect(bg_rect, QColor("#f0f9ff"))
            painter.drawText(bg_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, display_text)
        
        if self.is_interactive:
            pen = QPen(QColor("#0078d4"), 4)
            pen.setStyle(Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            painter.drawRect(self.rect().adjusted(2, 2, -2, -2))
        
        top_margin = 50 if self.show_title else 20
        widget_width = self.width()
        widget_height = self.height()
        cell_width = (widget_width - 40) / self.cols
        cell_height = (widget_height - top_margin - 20) / self.rows
        
        active_sample_wells = set()
        actual_start_pos = self.start_pos
        
        if self.sample_count > 0:
            # Skip disabled wells at the start
            while actual_start_pos in self.disabled_wells and actual_start_pos <= 96:
                actual_start_pos += 1
            
            count = 0
            current_pos = actual_start_pos
            
            while count < self.sample_count and current_pos <= 96:
                if current_pos not in self.disabled_wells:
                    active_sample_wells.add(current_pos)
                    count += 1
                current_pos += 1
        small_font = QFont("Arial", 11, QFont.Bold)
        for row in range(self.rows):
            for col in range(self.cols):
                well_index_1_based = (col * self.rows) + row + 1; color_outline = QColor("#000000"); color_fill = QColor("#FFFFFF")
                if well_index_1_based in self.disabled_wells:
                    color_fill = QColor("#e0e0e0")  # Lighter gray for better contrast
                elif well_index_1_based in active_sample_wells:
                    if well_index_1_based == actual_start_pos:
                        color_fill = QColor("#00b347")  # Deeper green for start position
                    else:
                        color_fill = QColor("#80dda8")  # Softer green for active samples
                elif well_index_1_based < self.start_pos:
                    color_fill = QColor("#ffd700")  # More saturated yellow for better visibility
                if self.is_interactive and well_index_1_based == self.temp_selected_well:
                    color_fill = QColor("#0078d4")  # Match the app's accent color
                rect = QRect(20 + col * cell_width, top_margin + row * cell_height, cell_width - 2, cell_height - 2)
                painter.setPen(QPen(color_outline, 2)); painter.setBrush(QBrush(color_fill))
                if self.shape == 'circle': painter.drawEllipse(rect)
                else: painter.drawRect(rect)
                well_name = f"{self.row_map[row]}{col + 1}"; painter.setFont(small_font)
                if color_fill.lightness() < 128: painter.setPen(QPen(QColor("#FFFFFF")))
                else: painter.setPen(QPen(QColor("#000000")))
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, well_name)
    def mousePressEvent(self, event):
        if not self.is_interactive: return
        top_margin = 50 if self.show_title else 20
        widget_width = self.width(); widget_height = self.height(); cell_width = (widget_width - 40) / self.cols; cell_height = (widget_height - top_margin - 20) / self.rows
        col = int((event.position().x() - 20) / cell_width); row = int((event.position().y() - top_margin) / cell_height)
        if 0 <= col < self.cols and 0 <= row < self.rows:
            well_index = (col * self.rows) + row + 1
            if well_index in self.disabled_wells:
                print(f"Brønn {well_index} er deaktivert og kan ikke velges."); return
            self.well_clicked.emit(well_index)

class NumericKeypad(QWidget):
    key_pressed = Signal(str)
    enter_pressed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        
        layout = QGridLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)
        
        buttons = {
            '7': (0, 0), '8': (0, 1), '9': (0, 2),
            '4': (1, 0), '5': (1, 1), '6': (1, 2),
            '1': (2, 0), '2': (2, 1), '3': (2, 2),
            'Slett': (3, 0), '0': (3, 1), 'Enter': (3, 2)
        }

        for text, pos in buttons.items():
            button = QPushButton(text)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            button.setMinimumHeight(80)  # Ensure good touch target size
            button.setFont(QFont("Arial", 32, QFont.Bold))
            
            # Special styling for Enter and Delete buttons
            special_style = ""
            if text == "Enter":
                special_style = """
                    background-color: #0078d4 !important;
                    color: white !important;
                    border-color: #005a9e !important;
                """
            elif text == "Slett":
                special_style = """
                    background-color: #d83b01 !important;
                    color: white !important;
                    border-color: #a62f00 !important;
                """
                
            button.setStyleSheet(f"""
                QPushButton {{
                    background-color: white;
                    border: 3px solid #404040;
                    border-radius: 8px;
                    padding: 12px;
                    color: #000000;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: #f0f9ff;
                    border-color: #0078d4;
                    color: #0078d4;
                }}
                QPushButton:pressed {{
                    background-color: #0078d4;
                    border-color: #005a9e;
                    color: white;
                }}
                {special_style}
            """)
            button.clicked.connect(self._on_button_click)
            layout.addWidget(button, pos[0], pos[1])
            
    def _on_button_click(self):
        button = self.sender()
        key = button.text()
        
        if key == "Slett":
            self.key_pressed.emit("del")
        elif key == "Enter":
            self.enter_pressed.emit()
        else:
            self.key_pressed.emit(key)
            # Let the parent handle selection reset