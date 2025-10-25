from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget, QSizePolicy
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QFont

from gui_widgets import WellPlateWidget
from custom_widgets import NumericDisplay
from box_group_summary import BoxGroupSummaryWidget

class BoxGroupWidget(QFrame):
    volume_display_clicked = Signal(object)
    change_start_pos_clicked = Signal(object)

    def __init__(self, group_data, parent=None):
        super().__init__(parent)
        self.group_data = group_data
        if 'currentStartPosition' not in self.group_data:
            self.group_data['currentStartPosition'] = self.group_data['initialStartPosition']
        self.plate_widgets = []
        self.sample_mapping = None
        self.setFrameShape(QFrame.Shape.StyledPanel)
        
        # Set size policy to prevent overflow
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumWidth(300)
        
        self._setup_ui()
        self.update_displays()
    
    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        
        name_label = QLabel(self.group_data.get("groupName", "Boksgruppe"))
        name_label.setFont(QFont("Arial", 24, QFont.Bold))
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setWordWrap(True)
        
        # Add summary widget for pooled scripts
        self.summary_widget = BoxGroupSummaryWidget()
        self.summary_widget.hide()  # Hidden by default
        
        controls_layout = QVBoxLayout()
        controls_layout.setSpacing(5)
        self._setup_controls(controls_layout)

        self.plates_container = QWidget()
        self.plates_layout = QVBoxLayout(self.plates_container)
        
        main_layout.addWidget(name_label)
        main_layout.addWidget(self.summary_widget)
        main_layout.addLayout(controls_layout)
        main_layout.addWidget(self.plates_container, stretch=1)

    def _setup_controls(self, layout):
        # Volume section - label above input
        volume_label = QLabel("Volum (µL):")
        volume_label.setFont(QFont("Arial", 18))
        volume_label.setAlignment(Qt.AlignCenter)
        
        self.volume_display = NumericDisplay()
        self.volume_display.setMaximumHeight(60)
        
        # Button section
        self.change_pos_button = QPushButton("Endre startposisjon")
        self.change_pos_button.setFont(QFont("Arial", 16))
        self.change_pos_button.setMinimumHeight(50)
        self.change_pos_button.setWordWrap(True)

        layout.addWidget(volume_label)
        layout.addWidget(self.volume_display)
        layout.addWidget(self.change_pos_button)
        
        self.volume_display.clicked.connect(lambda: self.volume_display_clicked.emit(self))
        self.change_pos_button.clicked.connect(lambda: self.change_start_pos_clicked.emit(self))

    def update_displays(self):
        volume = self.group_data.get('volume', {}).get('defaultValue', 0)
        self.volume_display.setText(str(volume))
        
        # Update all plate widgets with current start position
        for plate in self.plate_widgets:
            plate.start_pos = self.group_data.get('currentStartPosition', 1)
            plate.update()

    def update_plates(self, total_samples, start_pos, disabled_wells, sample_data=None):
        try:
            # Clear existing plates
            while self.plates_layout.count():
                child = self.plates_layout.takeAt(0)
                if child.widget(): 
                    child.widget().deleteLater()
            self.plate_widgets.clear()

            # Get group settings
            frame_color = self.group_data.get("color", "#808080")
            group_type = self.group_data.get("groupType", "standard")
            max_boxes = self.group_data.get("maxBoxes", 1)
            
            # Update summary widget for pooled script types
            if group_type in ["individual", "pooled"] and sample_data:
                print(f"BoxGroupWidget: Using {group_type} sample data with {len(sample_data)} samples")
                self.summary_widget.show()
                self.summary_widget.update_summary(group_type, sample_data)
                # Use actual sample count from data
                samples_to_distribute = len(sample_data)
                print(f"BoxGroupWidget: samples_to_distribute set to {samples_to_distribute}")
            else:
                self.summary_widget.hide()
                samples_to_distribute = total_samples
                print(f"BoxGroupWidget: Using standard sample count: {samples_to_distribute}")

            # Create plates as needed
            current_pos = start_pos
            samples_remaining = samples_to_distribute
            
            for box_num in range(max_boxes):
                if samples_remaining <= 0:
                    break
                    
                show_title = (box_num == 0)  # Only first plate shows title
                plate = WellPlateWidget(
                    shape=self.group_data.get("shape", "rect"),
                    show_title=show_title
                )
                
                # Calculate samples for this plate
                available_wells = sum(1 for well in range(current_pos, 97)
                                   if well not in disabled_wells)
                samples_this_plate = min(samples_remaining, available_wells)
                
                # Make sure we have at least one sample to display
                if samples_this_plate > 0:
                    # Set plate state with guaranteed sample count
                    plate.set_state(
                        start_pos=current_pos,
                        sample_count=samples_this_plate,
                        disabled_wells=disabled_wells,
                        frame_color=frame_color
                    )
                
                self.plates_layout.addWidget(plate)
                self.plate_widgets.append(plate)
                
                # Update counters
                samples_remaining -= samples_this_plate
                current_pos = 1  # Start at beginning for subsequent plates
                
        except Exception as e:
            print(f"Error updating plates: {e}")
            return