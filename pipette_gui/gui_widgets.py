# Filnavn: gui_widgets.py

from PySide6.QtWidgets import QWidget, QPushButton, QGridLayout, QVBoxLayout, QLabel, QSizePolicy
from PySide6.QtCore import Signal, Qt, QRect
from PySide6.QtGui import QPainter, QColor, QBrush, QPen, QFont, QPixmap

class ThumbnailButton(QWidget):
    # ... (Denne klassen er uendret)
    clicked = Signal()
    def __init__(self, text, image_path, parent=None):
        super().__init__(parent); self.setFixedSize(250, 200); main_layout = QVBoxLayout(self); main_layout.setContentsMargins(10, 10, 10, 10); self.image_label = QLabel(); self.image_label.setAlignment(Qt.AlignCenter); self.image_label.setScaledContents(True); pixmap = QPixmap(image_path)
        if pixmap.isNull(): self.image_label.setText("Bilde\nikke funnet")
        else: self.image_label.setPixmap(pixmap)
        self.text_label = QLabel(text); self.text_label.setFont(QFont("Arial", 16, QFont.Bold)); self.text_label.setAlignment(Qt.AlignCenter); self.text_label.setWordWrap(True); main_layout.addWidget(self.image_label, 1); main_layout.addWidget(self.text_label)
        self.setStyleSheet("""ThumbnailButton { background-color: #f0f0f0; border: 1px solid #ccc; border-radius: 8px; } ThumbnailButton:hover { background-color: #aadeff; }""")
    def mousePressEvent(self, event):
        self.clicked.emit(); super().mousePressEvent(event)

class WellPlateWidget(QWidget):
    # ... (Denne klassen er uendret)
    well_clicked = Signal(int)
    def __init__(self, shape='rect', fixed_size=True, show_title=True, parent=None):
        super().__init__(parent)
        self.rows = 8; self.cols = 12; self.start_pos = 1; self.sample_count = 0; self.disabled_wells = []; self.shape = shape; self.is_interactive = False; self.temp_selected_well = None
        self.row_map = {i: chr(ord('A') + i) for i in range(self.rows)}
        self.show_title = show_title
        if fixed_size:
            self.setFixedSize(520, 380)
    def index_to_coord(self, index):
        if not 1 <= index <= 96: return "?"
        row = (index - 1) % 8; col = (index - 1) // 8
        return f"{chr(ord('A') + row)}{col + 1}"
    def set_state(self, start_pos, sample_count, disabled_wells):
        self.start_pos = start_pos; self.sample_count = sample_count; self.disabled_wells = disabled_wells; self.update()
    def set_interactive(self, interactive):
        self.is_interactive = interactive
        if not interactive: self.temp_selected_well = None
        self.update()
    def paintEvent(self, event):
        painter = QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.show_title:
            painter.setFont(QFont("Arial", 20, QFont.Bold)); painter.setPen(QColor("#0078d4")); coord_text = self.index_to_coord(self.start_pos); display_text = f"Startposisjon: {coord_text}"; painter.drawText(self.rect().adjusted(0, 5, 0, 0), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, display_text)
        if self.is_interactive:
            pen = QPen(QColor("#0078d4"), 4); pen.setStyle(Qt.PenStyle.SolidLine)
            painter.setPen(pen); painter.drawRect(self.rect().adjusted(2, 2, -2, -2))
        top_margin = 50 if self.show_title else 20
        widget_width = self.width(); widget_height = self.height(); cell_width = (widget_width - 40) / self.cols; cell_height = (widget_height - top_margin - 20) / self.rows
        active_sample_wells = set(); actual_start_pos = self.start_pos
        if self.sample_count > 0:
            while actual_start_pos in self.disabled_wells and actual_start_pos <= 96: actual_start_pos += 1
            count = 0; current_pos = actual_start_pos
            while count < self.sample_count and current_pos <= 96:
                if current_pos not in self.disabled_wells: active_sample_wells.add(current_pos); count += 1
                current_pos += 1
        small_font = QFont("Arial", 10)
        for row in range(self.rows):
            for col in range(self.cols):
                well_index_1_based = (col * self.rows) + row + 1; color_outline = QColor("#000000"); color_fill = QColor("#FFFFFF")
                if well_index_1_based in self.disabled_wells: color_fill = QColor("#a0a0a0")
                elif well_index_1_based in active_sample_wells:
                    if well_index_1_based == actual_start_pos: color_fill = QColor("#009933")
                    else: color_fill = QColor("#99ff99")
                elif well_index_1_based < self.start_pos: color_fill = QColor("#ffff99")
                if self.is_interactive and well_index_1_based == self.temp_selected_well: color_fill = QColor("#3399ff")
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
    # FIKS: Endret signalnavn for klarhet
    enter_pressed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QGridLayout(self)
        layout.setSpacing(10)
        
        # FIKS: Oppdatert layout for knapper
        buttons = {
            '7': (0, 0), '8': (0, 1), '9': (0, 2),
            '4': (1, 0), '5': (1, 1), '6': (1, 2),
            '1': (2, 0), '2': (2, 1), '3': (2, 2),
            'Slett': (3, 0), '0': (3, 1), 'Enter': (3, 2)
        }

        for text, pos in buttons.items():
            button = QPushButton(text)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            button.setFont(QFont("Arial", 30))
            button.clicked.connect(self._on_button_click)
            layout.addWidget(button, pos[0], pos[1])
            
    def _on_button_click(self):
        button = self.sender()
        key = button.text()
        
        # FIKS: Logikk for Enter-knappen
        if key == "Slett":
            self.key_pressed.emit("del")
        elif key == "Enter":
            self.enter_pressed.emit()
        else:
            self.key_pressed.emit(key)