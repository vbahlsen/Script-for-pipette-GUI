from PySide6.QtWidgets import QLineEdit
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

class NumericDisplay(QLineEdit):
    """A custom widget for displaying numeric input that works with the numeric keypad."""
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)  # Make it read-only since input comes from keypad
        self.setAlignment(Qt.AlignCenter)
        self.setFont(QFont("Arial", 28, QFont.Bold))
        self.setMinimumWidth(140)
        self.setMinimumHeight(60)  # Ensure good touch target size
        
        # Create a base style with darker focus state
        base_style = """
            QLineEdit {
                background-color: white;
                border: 3px solid #404040;
                border-radius: 8px;
                padding: 8px;
                color: #000000;
                font-family: Arial;
                font-size: 28pt;
                font-weight: bold;
            }
            QLineEdit:focus {
                background-color: #005a9e;
                border: 3px solid #004578;
                color: white;
            }
            QLineEdit:disabled {
                background-color: #f0f0f0;
                border-color: #cccccc;
                color: #666666;
            }
        """
        # Apply the style sheet at a higher specificity
        self.setStyleSheet(base_style)
        
    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self.clicked.emit()
        # Select all text when clicked
        self.selectAll()