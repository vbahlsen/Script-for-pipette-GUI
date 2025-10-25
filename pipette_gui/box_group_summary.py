from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

class BoxGroupSummaryWidget(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        
        layout = QVBoxLayout(self)
        
        # Create labels with consistent styling
        self.title_label = QLabel()
        self.title_label.setFont(QFont("Arial", 24, QFont.Bold))
        self.title_label.setAlignment(Qt.AlignCenter)
        
        self.count_label = QLabel()
        self.count_label.setFont(QFont("Arial", 20))
        self.count_label.setAlignment(Qt.AlignCenter)
        
        self.details_label = QLabel()
        self.details_label.setFont(QFont("Arial", 16))
        self.details_label.setAlignment(Qt.AlignLeft)
        self.details_label.setWordWrap(True)
        
        # Add widgets to layout
        layout.addWidget(self.title_label)
        layout.addWidget(self.count_label)
        layout.addWidget(self.details_label)
    
    def update_summary(self, group_type, sample_data=None):
        """Update the summary display based on group type and sample data"""
        if group_type == "individual":
            self.title_label.setText("Individuelle Prøver")
            if sample_data:
                count = len(sample_data)
                self.count_label.setText(f"Antall prøver: {count}")
                
                # Create case summary
                case_counts = {}
                for sample in sample_data:
                    case_id = sample['case_id']
                    if case_id not in case_counts:
                        case_counts[case_id] = 0
                    case_counts[case_id] += 1
                
                details = "Fordeling per journalsak:\n"
                for case_id, count in case_counts.items():
                    details += f"• {case_id}: {count} prøver\n"
                self.details_label.setText(details)
            else:
                self.count_label.setText("Ingen prøver")
                self.details_label.setText("")
                
        elif group_type == "pooled":
            self.title_label.setText("Samleprøver")
            if sample_data:
                count = len(sample_data)
                self.count_label.setText(f"Antall samleprøver: {count}")
                self.details_label.setText("En samleprøve per journalsak:")
            else:
                self.count_label.setText("Ingen samleprøver")
                self.details_label.setText("")