# Filnavn: gui_screens.py

import os
import json
import math
import subprocess
import re
import shutil
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                               QLabel, QSpacerItem, QSizePolicy, QFrame, QScrollArea, 
                               QCheckBox, QFormLayout, QLineEdit, QComboBox, QMessageBox, 
                               QTextEdit, QRadioButton, QButtonGroup, QGroupBox, QGridLayout, QScroller, QFileDialog)
from PySide6.QtCore import Signal, Qt, QPoint
from PySide6.QtGui import QFont, QIntValidator, QPixmap, QPainter, QColor
from PySide6.QtWidgets import QApplication

from gui_widgets import WellPlateWidget, NumericKeypad, ThumbnailButton
from custom_widgets import NumericDisplay
from box_group_summary import BoxGroupSummaryWidget
from box_group_widget import BoxGroupWidget
from journal_data import JournalData


def _initial_dir_from_path(path_text: str) -> str:
    path_text = (path_text or "").strip()
    if not path_text:
        return ""
    if os.path.isdir(path_text):
        return path_text
    parent = os.path.dirname(path_text)
    return parent if os.path.isdir(parent) else ""


def make_path_picker(parent: QWidget, line_edit: QLineEdit, *,
                     mode: str = "open",
                     caption: str = "Velg fil",
                     file_filter: str = "Alle filer (*)") -> QWidget:
    """Wrap a QLineEdit with a browse button on the right."""
    container = QWidget(parent)
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)

    btn = QPushButton("📂", container)
    btn.setToolTip(caption)
    btn.setFixedSize(48, 48)

    layout.addWidget(line_edit, 1)
    layout.addWidget(btn, 0)

    def _browse():
        start_dir = _initial_dir_from_path(line_edit.text())
        if mode == "dir":
            selected = QFileDialog.getExistingDirectory(parent, caption, start_dir)
            if selected:
                line_edit.setText(selected)
            return

        if mode == "save":
            selected, _ = QFileDialog.getSaveFileName(parent, caption, line_edit.text() or start_dir, file_filter)
        else:
            selected, _ = QFileDialog.getOpenFileName(parent, caption, line_edit.text() or start_dir, file_filter)
        if selected:
            line_edit.setText(selected)

    btn.clicked.connect(_browse)
    return container

class ScriptSelectorScreen(QWidget):
    script_selected = Signal(dict); settings_clicked = Signal()
    def __init__(self, base_dir, parent=None):
        super().__init__(parent); self.base_dir = base_dir; self.scripts_dir = base_dir / "scripts"; self.main_layout = QVBoxLayout(self); self.main_layout.setContentsMargins(10, 10, 10, 10); title = QLabel("Velg script"); title.setFont(QFont("Arial", 48, QFont.Bold)); self.main_layout.addWidget(title, alignment=Qt.AlignCenter); scroll_area = QScrollArea(); scroll_area.setWidgetResizable(True); scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff); scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded); 
        
        # Enable touch scrolling for better touchscreen support
        QScroller.grabGesture(scroll_area.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)
        
        self.button_container = QWidget(); self.button_layout = QGridLayout(self.button_container); self.button_layout.setSpacing(15); self.button_layout.setContentsMargins(10, 10, 10, 10); self.button_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter); scroll_area.setWidget(self.button_container); self.main_layout.addWidget(scroll_area, 1); bottom_bar_layout = QHBoxLayout(); settings_button = QPushButton("⚙️"); settings_button.setFont(QFont("Arial", 30)); settings_button.setFixedSize(80, 80); settings_button.clicked.connect(self.settings_clicked.emit); bottom_bar_layout.addStretch(1); bottom_bar_layout.addWidget(settings_button); self.main_layout.addLayout(bottom_bar_layout)
    def clear_buttons(self):
        while self.button_layout.count():
            item = self.button_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
    def load_scripts(self):
        self.clear_buttons()
        try:
            with open("settings.json", 'r') as f: settings = json.load(f)
            inactive_scripts = settings.get("inactive_scripts", [])
        except FileNotFoundError: inactive_scripts = []
        if not os.path.exists(self.scripts_dir): return
        scripts_to_show = []
        for dir_name in sorted(os.listdir(self.scripts_dir)):
            config_path = self.scripts_dir / dir_name / 'config.json'
            if config_path.is_file() and dir_name not in inactive_scripts:
                try:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        script_data = json.load(f); script_data['folder_name'] = dir_name; scripts_to_show.append(script_data)
                except Exception as e: print(f"Kunne ikke laste {config_path}: {e}")
        cols = 2  # Use 2 columns for vertical screens to avoid horizontal overflow
        for i, script_data in enumerate(scripts_to_show):
            row, col = divmod(i, cols); image_path = self.scripts_dir / script_data['folder_name'] / script_data.get('thumbnail', ''); button = ThumbnailButton(script_data['scriptName'], str(image_path)); button.clicked.connect(lambda data=script_data: self.script_selected.emit(data)); self.button_layout.addWidget(button, row, col)

class BoxGroupWidget(QFrame):
    volume_display_clicked = Signal(object)
    change_start_pos_clicked = Signal(object)

    def __init__(self, group_data, parent=None):
        super().__init__(parent)
        self.group_data = group_data
        if 'currentStartPosition' not in self.group_data:
            self.group_data['currentStartPosition'] = self.group_data['initialStartPosition']
        self.plate_widgets = []
        self.sample_mapping = None  # Will store mapping for pooled scripts
        self.setFrameShape(QFrame.Shape.StyledPanel)
        
        # Set size policy to prevent overflow
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumWidth(300)
        
        self._setup_ui()
        self.update_displays()
    
    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(8, 8, 8, 8)  # Add margins to prevent cutoff
        
        name_label = QLabel(self.group_data.get("groupName", "Boksgruppe"))
        name_label.setFont(QFont("Arial", 22, QFont.Bold))
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setWordWrap(True)
        
        # Add summary widget for pooled scripts
        self.summary_widget = BoxGroupSummaryWidget()
        self.summary_widget.hide()  # Hidden by default, shown only for pooled scripts
        
        controls_layout = QVBoxLayout()
        controls_layout.setSpacing(5)
        self._setup_controls(controls_layout)

        self.plates_container = QWidget()
        self.plates_layout = QVBoxLayout(self.plates_container)
        self.plates_layout.setContentsMargins(5, 5, 5, 5)  # Add margins around plates
        self.plates_layout.setSpacing(5)
        
        main_layout.addWidget(name_label)
        main_layout.addWidget(self.summary_widget)
        main_layout.addLayout(controls_layout)
        main_layout.addWidget(self.plates_container, stretch=1)

    def _setup_controls(self, layout):
        # Volume section - label above input
        volume_label = QLabel("Volum (µL):")
        volume_label.setFont(QFont("Arial", 16))
        volume_label.setAlignment(Qt.AlignCenter)
        
        self.volume_display = NumericDisplay()
        self.volume_display.setMaximumHeight(60)
        
        # Button section
        self.change_pos_button = QPushButton("Endre startposisjon")
        self.change_pos_button.setFont(QFont("Arial", 14))
        self.change_pos_button.setMinimumHeight(45)

        layout.addWidget(volume_label)
        layout.addWidget(self.volume_display)
        layout.addWidget(self.change_pos_button)
        
        self.volume_display.clicked.connect(lambda: self.volume_display_clicked.emit(self))
        self.change_pos_button.clicked.connect(lambda: self.change_start_pos_clicked.emit(self))

    def update_displays(self):
        volume = self.group_data.get('volume', {}).get('defaultValue', 0)
        self.volume_display.setText(str(volume))
        for plate in self.plate_widgets:
            plate.start_pos = self.group_data.get('currentStartPosition', 1)
            plate.update()

    def update_plates(self, sample_count, start_pos, disabled_wells, sample_data=None):
        try:
            # Clear existing plates
            while self.plates_layout.count():
                child = self.plates_layout.takeAt(0)
                if child.widget(): 
                    child.widget().deleteLater()
            self.plate_widgets.clear()

            # Get frame color
            frame_color = self.group_data.get("color", "#808080")
            group_type = self.group_data.get("groupType", "standard")
            
            # Update summary for pooled script types
            if group_type in ["individual", "pooled"]:
                self.summary_widget.show()
                self.summary_widget.update_summary(group_type, sample_data)
            else:
                self.summary_widget.hide()

            # Handle empty state
            if sample_count <= 0:
                plate = WellPlateWidget(shape=self.group_data.get("shape", "rect"), fixed_size=False, show_title=True)
                plate.set_state(start_pos=start_pos, sample_count=0, disabled_wells=disabled_wells, frame_color=frame_color)
                # Make the imaged plate clickable to open the expanded start-position editor,
                # matching the "Endre startposisjon" button behavior.
                plate.setCursor(Qt.CursorShape.PointingHandCursor)
                plate.plate_clicked.connect(lambda _gw=self: self.change_start_pos_clicked.emit(_gw))
                # Don't set fixed size - let it scale with container
                self.plates_layout.addWidget(plate)
                self.plate_widgets.append(plate)
                return

        except Exception as e:
            print(f"Error updating plates: {e}")
            return

        samples_to_distribute = sample_count
        num_plates_to_show = self.group_data.get("maxBoxes", 1)
        current_pos_on_plate = start_pos
        
        for i in range(num_plates_to_show):
            if samples_to_distribute <= 0:
                break

            show_title = (i == 0)
            plate = WellPlateWidget(shape=self.group_data.get("shape", "rect"), fixed_size=False, show_title=show_title)
            # Make the imaged plate clickable to open the expanded start-position editor,
            # matching the "Endre startposisjon" button behavior.
            plate.setCursor(Qt.CursorShape.PointingHandCursor)
            plate.plate_clicked.connect(lambda _gw=self: self.change_start_pos_clicked.emit(_gw))

            available_wells_on_this_plate = 0
            for well in range(current_pos_on_plate, 97):
                if well not in disabled_wells:
                    available_wells_on_this_plate += 1
            
            samples_on_this_plate = min(samples_to_distribute, available_wells_on_this_plate)
            
            try:
                # Handle missing color field gracefully
                if "color" in self.group_data:
                    frame_color = self.group_data["color"]
                else:
                    frame_color = "#808080"  # Default gray for older configs
                    
                plate.set_state(start_pos=current_pos_on_plate, 
                              sample_count=samples_on_this_plate, 
                              disabled_wells=disabled_wells,
                              frame_color=frame_color)
            except Exception as e:
                print(f"Error setting plate state: {e}")
                # Fallback to basic state without color
                plate.set_state(start_pos=current_pos_on_plate, 
                              sample_count=samples_on_this_plate, 
                              disabled_wells=disabled_wells)
            
            # Don't set fixed size - let it scale with container
            # plate.setMaximumWidth(450)  # Removed to allow proper scaling
            
            self.plates_layout.addWidget(plate)
            self.plate_widgets.append(plate)

            samples_to_distribute -= samples_on_this_plate
            current_pos_on_plate = 1

    def index_to_coord(self, index):
        if not 1 <= index <= 96: return "Ugyldig"
        row = (index - 1) % 8
        col = (index - 1) // 8
        return f"{chr(ord('A') + row)}{col + 1}"

class ScriptDetailScreen(QWidget):
    back_to_menu = Signal(); edit_plate_fullscreen = Signal(object)
    def __init__(self, base_dir, parent=None):
        super().__init__(parent)
        self.base_dir = base_dir
        self.box_group_widgets = []
        self.active_group_for_editing = None
        self.active_input_display = None
        self.udf_widgets = []
        self.temp_sample_input = "0"  # Store temporary value until confirmed
        self.journal_data = JournalData()  # For handling pooled samples
        self._setup_ui(QVBoxLayout(self))
        self._connect_signals()
    def load_script_data(self, script_data):
        """
        Load script data and prepare the UI.
        Returns True if loading was successful, False otherwise.
        """
        import os
        import re
        from pathlib import Path
        
        self.keypad.hide()
        self.script_data = script_data
        
        # Clear existing box groups
        while self.groups_layout.count():
            child = self.groups_layout.takeAt(0)
            if child.widget(): 
                child.widget().deleteLater()
        self.box_group_widgets.clear()

        # Load journal data for pooled scripts
        sample_mapping = None
        if script_data.get("scriptType") == "pooled":
            script_dir = self.base_dir / "scripts" / script_data['folder_name']
            journal_path = script_data.get('journalDataFile', '').strip()
            
            # Determine the actual file path
            journal_file_path = None
            
            if journal_path:
                # Remove trailing slashes/backslashes
                journal_path = journal_path.rstrip('/\\')
                
                # Check if it's a directory or file
                if os.path.isdir(journal_path):
                    # It's a directory - search for files in it
                    search_dir = Path(journal_path)
                    txt_files = list(search_dir.glob("*.txt"))
                    csv_files = list(search_dir.glob("*.csv"))
                    journal_files = txt_files + csv_files
                    
                    if len(journal_files) > 1:
                        QMessageBox.warning(self, "Flere journalfiler", 
                                          f"Flere lister i {search_dir}, rydd opp i disse og prøv igjen")
                        return False
                    elif len(journal_files) == 1:
                        journal_file_path = str(journal_files[0])
                elif os.path.isfile(journal_path):
                    # It's a file - use it directly
                    journal_file_path = journal_path
                else:
                    # Path doesn't exist - try as relative path
                    potential_path = script_dir / journal_path
                    if potential_path.is_file():
                        journal_file_path = str(potential_path)
                    elif potential_path.is_dir():
                        # It's a relative directory
                        txt_files = list(potential_path.glob("*.txt"))
                        csv_files = list(potential_path.glob("*.csv"))
                        journal_files = txt_files + csv_files
                        
                        if len(journal_files) > 1:
                            QMessageBox.warning(self, "Flere journalfiler", 
                                              f"Flere lister i {potential_path}, rydd opp i disse og prøv igjen")
                            return False
                        elif len(journal_files) == 1:
                            journal_file_path = str(journal_files[0])
            
            # If still no file found, search in script directory as fallback
            if not journal_file_path:
                txt_files = list(script_dir.glob("*.txt"))
                csv_files = list(script_dir.glob("*.csv"))
                journal_files = txt_files + csv_files
                
                if len(journal_files) > 1:
                    QMessageBox.warning(self, "Flere journalfiler", 
                                      f"Flere lister i {script_dir}, rydd opp i disse og prøv igjen")
                    return False
                elif len(journal_files) == 1:
                    journal_file_path = str(journal_files[0])
                else:
                    QMessageBox.warning(self, "Mangler journalfil", 
                                      f"Ingen journalfiler funnet")
                    return False
            
            # Load the journal file
            if journal_file_path and self.journal_data.load_file(journal_file_path):
                sample_mapping = self.journal_data.get_sample_mapping()
                # Set up display for pooled scripts
                self.samples_display.setEnabled(False)
                
                # Get sample counts
                individual_count = len(sample_mapping["individual"])
                pool_count = len(sample_mapping["pooled"])
                self.samples_display.setText(str(individual_count))
                
                # Create sample count label if it doesn't exist
                if not hasattr(self, 'pooled_info_label'):
                    self.pooled_info_label = QLabel()
                    self.pooled_info_label.setFont(QFont("Arial", 16))
                    index = self.main_layout.indexOf(self.sample_range_label)
                    self.main_layout.insertWidget(index + 1, self.pooled_info_label)
                
                # Update pooled sample information - get first and last from ordered list
                first_case = sample_mapping["individual"][0]["case_id"] if sample_mapping["individual"] else ""
                last_case = sample_mapping["individual"][-1]["case_id"] if sample_mapping["individual"] else ""
                
                self.pooled_info_label.setText(
                    f"Antall journalsaker: {pool_count}\n"
                    f"Første og siste journalsak: {first_case} til {last_case}")
                self.pooled_info_label.show()
            else:
                QMessageBox.warning(self, "Kunne ikke laste journalfil", 
                                  f"Feil ved lasting av journalfil")
                return False
        else:
            # Enable sample count input for standard scripts
            self.samples_display.setEnabled(True)
            
            # Hide pooled info label for standard scripts
            if hasattr(self, 'pooled_info_label'):
                self.pooled_info_label.hide()
        
        def _read_start_position_from_file(path_value):
            if not path_value:
                return None

            start_pos_path = os.path.normpath(str(path_value))
            try:
                # utf-8-sig handles files that may include a UTF-8 BOM (common on Windows)
                with open(start_pos_path, 'r', encoding='utf-8-sig') as f:
                    raw_text = f.read()

                match = re.search(r"\d+", raw_text.strip())
                if not match:
                    print(f"WARNING: startPositionFile contains no number: {start_pos_path} (content={raw_text!r})")
                    return None

                pos_from_file = int(match.group(0))
                if 1 <= pos_from_file <= 96:
                    return pos_from_file

                print(f"WARNING: startPositionFile out of range (1-96): {start_pos_path} (value={pos_from_file})")
                return None
            except FileNotFoundError:
                print(f"WARNING: startPositionFile not found: {start_pos_path}")
                return None
            except PermissionError as e:
                print(f"WARNING: startPositionFile not readable: {start_pos_path} ({e})")
                return None
            except OSError as e:
                print(f"WARNING: error reading startPositionFile: {start_pos_path} ({e})")
                return None

        # Create box group widgets
        for group_data in self.script_data.get("boxGroups", []):
            try:
                # Load start position (prefer previously saved file value)
                start_pos = _read_start_position_from_file(group_data.get('startPositionFile'))
                group_data['currentStartPosition'] = (
                    start_pos if start_pos is not None else group_data['initialStartPosition']
                )
            except KeyError:
                group_data['currentStartPosition'] = 1

            # Create and set up group widget
            group_widget = BoxGroupWidget(group_data)
            group_widget.volume_display_clicked.connect(self._on_volume_display_clicked)
            group_widget.change_start_pos_clicked.connect(self._on_change_start_pos_clicked)

            # Set sample data for pooled scripts
            if sample_mapping and group_data.get("groupType") in ["individual", "pooled"]:
                # Get samples specific to this group type
                group_samples = sample_mapping[group_data["groupType"]]
                sample_count = len(group_samples)
                
                print(f"Setting up {group_data['groupType']} group with {sample_count} samples")
                
                # Update plates with specific sample data
                group_widget.update_plates(
                    sample_count, 
                    group_data['currentStartPosition'], 
                    group_data.get('disabledWells', []), 
                    group_samples
                )
            
            self.groups_layout.addWidget(group_widget)
            self.box_group_widgets.append(group_widget)

        # Reset UI state
        if not sample_mapping:
            self.samples_input = ""
            self.samples_display.setText("0")
            
        self.start_button.setEnabled(False)
        self._set_active_input(None)
        self.script_name_label.setText(self.script_data.get("scriptName", "Ukjent Script"))
        self.description_label.setText(self.script_data.get("description", "")); sample_range = self.script_data.get("sampleRange", {}); min_s, max_s = sample_range.get("min", 1), sample_range.get("max", 96); self.sample_range_label.setText(f"Gyldig antall: {min_s} - {max_s}")
        self.thumbnail_label.clear(); thumbnail_path = script_data.get("thumbnail", "")
        if thumbnail_path:
            full_path = self.base_dir / "scripts" / script_data['folder_name'] / thumbnail_path
            if os.path.exists(full_path):
                pixmap = QPixmap(str(full_path)); self.thumbnail_label.setPixmap(pixmap)
            else: self.thumbnail_label.setText("Bilde\nikke\nfunnet")
        # Clear existing UDF widgets
        for udf_widget in self.udf_widgets:
            udf_widget["group"].deleteLater()
        self.udf_widgets.clear()
        
        # Get UDF list
        udf_list = self.script_data.get("userDefinedVariables", [])
            
        for udf_data in udf_list:
            if udf_data and udf_data.get("question"):
                question_text = udf_data.get("question")
                # Add "required" indicator
                required_text = f"{question_text} *"
                group_box = QGroupBox(required_text)
                group_box.setFont(QFont("Arial", 16))
                group_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
                layout = QVBoxLayout(group_box)
                layout.setSpacing(8)  # Slightly more spacing between options
                button_group = QButtonGroup(self)
                
                for i, option in enumerate(udf_data.get("options", [])):
                    if option.get("label"):
                        # Create a larger radio button with bigger font
                        radio = QRadioButton(option.get("label"))
                        radio.setFont(QFont("Arial", 14))
                        radio.setMinimumHeight(35)
                        
                        # Set a slightly larger indicator size
                        radio.setStyleSheet("""
                            QRadioButton::indicator {
                                width: 20px;
                                height: 20px;
                            }
                        """)
                        
                        layout.addWidget(radio)
                        button_group.addButton(radio, i)
                        
                        # Connect radio button to update button state when clicked
                        radio.clicked.connect(self._update_button_state)
                        
                # Add to main layout
                self.udf_main_layout.addWidget(group_box)
                
                # Store references
                self.udf_widgets.append({"group": group_box, "buttons": button_group, "data": udf_data})
        self._update_all_plates()
        
        # Return success
        return True
    def _setup_ui(self, main_layout):
        self.main_layout = main_layout; main_layout.setContentsMargins(0,0,0,0); scroll_area = QScrollArea(); scroll_area.setWidgetResizable(True); scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff); scroll_area.setStyleSheet("QScrollArea { border: none; }"); 
        
        # Enable touch scrolling for better touchscreen support
        QScroller.grabGesture(scroll_area.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)
        
        self.grab_container = QWidget(); scroll_area.setWidget(self.grab_container); content_layout = QVBoxLayout(self.grab_container); content_layout.setContentsMargins(10, 10, 10, 10); top_bar_layout = QHBoxLayout(); info_layout = QHBoxLayout(); self.back_button = QPushButton("← Tilbake til menyen"); self.back_button.setMinimumHeight(80); self.back_button.setFont(QFont("Arial", 18)); top_bar_layout.addWidget(self.back_button); top_bar_layout.addSpacerItem(QSpacerItem(20, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)); self.script_name_label = QLabel("Script Navn"); self.script_name_label.setFont(QFont("Arial", 28, QFont.Bold)); self.script_name_label.setAlignment(Qt.AlignCenter); self.script_name_label.setWordWrap(True); self.thumbnail_label = QLabel(); self.thumbnail_label.setMaximumSize(480, 340); self.thumbnail_label.setScaledContents(True); self.thumbnail_label.setAlignment(Qt.AlignCenter); self.thumbnail_label.setStyleSheet("border: 1px solid #ccc;"); self.description_label = QLabel("Beskrivelse her..."); self.description_label.setFont(QFont("Arial", 14)); self.description_label.setWordWrap(True); info_vbox = QVBoxLayout(); info_vbox.addWidget(self.description_label); info_vbox.addStretch(1); info_layout.addWidget(self.thumbnail_label); info_layout.addLayout(info_vbox); self.sample_range_label = QLabel("Gyldig antall: 1 - 96"); self.sample_range_label.setFont(QFont("Arial", 12, italic=True)); 
        samples_layout = QHBoxLayout()
        samples_label = QLabel("Antall prøver:")
        samples_label.setFont(QFont("Arial", 20))
        self.samples_display = NumericDisplay()
        self.samples_display.setText("0")
        self.samples_display.setMaximumWidth(200)
        samples_layout.addWidget(samples_label); samples_layout.addWidget(self.samples_display); samples_layout.addStretch(1); 
        self.udf_main_layout = QVBoxLayout()
        
        # Create a constrained container for box groups
        self.groups_container = QWidget()
        self.groups_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.groups_layout = QHBoxLayout(self.groups_container)
        self.groups_layout.setSpacing(10)
        self.groups_layout.setContentsMargins(5, 5, 5, 5)
        
        self.start_button = QPushButton("START PIPETTERING"); self.start_button.setMinimumHeight(120); self.start_button.setFont(QFont("Arial", 32, QFont.Bold)); self.start_button.setStyleSheet("""QPushButton {background-color: #0078d4; color: white;} QPushButton:disabled {background-color: #5a5a5a; color: #999999;}"""); self.keypad = NumericKeypad(self); self.keypad.setFixedSize(450, 520); self.keypad.hide(); content_layout.addLayout(top_bar_layout); content_layout.addWidget(self.script_name_label); content_layout.addLayout(info_layout); content_layout.addLayout(samples_layout); content_layout.addWidget(self.sample_range_label); content_layout.addLayout(self.udf_main_layout); content_layout.addWidget(self.groups_container); content_layout.addStretch(1); main_layout.addWidget(scroll_area, 1); main_layout.addWidget(self.start_button)
    def _connect_signals(self):
        self.back_button.clicked.connect(self.back_to_menu.emit); self.keypad.enter_pressed.connect(self._confirm_input); self.keypad.key_pressed.connect(self._on_key_pressed); self.samples_display.clicked.connect(lambda: self._set_active_input(self.samples_display)); self.start_button.clicked.connect(self._on_start_pipetting)
    def _confirm_input(self):
        if not self.active_input_display:
            return
            
        # Update based on the type of input
        if self.active_input_display == self.samples_display:
            # Update the actual sample count and refresh plates
            self.samples_input = self.temp_sample_input
            self._update_all_plates()
        else:
            # For volume inputs, the update is already done in _on_key_pressed
            pass
            
        # Hide keypad and clear focus
        self._hide_keypad()
    def _hide_keypad(self):
        # Reset to default style for all input fields
        default_style = """
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
        """
        self.samples_display.setStyleSheet(default_style)
        for group in self.box_group_widgets:
            if hasattr(group, 'volume_display'):
                group.volume_display.setStyleSheet(default_style)
        
        # Hide keypad and reset active input
        self.keypad.hide()
        self.active_input_display = None
    def finalize_new_start_pos(self, well_index):
        if self.active_group_for_editing:
            group = self.active_group_for_editing; group.group_data['currentStartPosition'] = well_index; group.update_displays(); self._update_all_plates(); self.active_group_for_editing = None
            
    def _check_udf_selections(self):
        """Check if all user-defined variables have selections"""
        # If there are no UDFs, return True
        if not self.udf_widgets:
            return True
            
        # Check each UDF widget to see if a selection has been made
        for udf_widget in self.udf_widgets:
            if udf_widget["buttons"].checkedId() == -1:  # No selection
                return False
        return True
            
    def _update_button_state(self):
        """Update the state of the Start Pipetting button based on samples and UDFs"""
        is_pooled = self.script_data.get("scriptType") == "pooled"
        num_samples = int(self.samples_input or "0")
        sample_mapping = None
        
        if is_pooled and hasattr(self, 'journal_data'):
            sample_mapping = self.journal_data.get_sample_mapping()
            
        # Check if we have valid sample count
        has_samples = num_samples > 0 or (is_pooled and sample_mapping is not None)
        
        # Check if all UDFs have selections
        all_udfs_selected = self._check_udf_selections()
        
        # Enable button only if we have samples AND all UDFs are selected
        self.start_button.setEnabled(has_samples and all_udfs_selected)
            
    def _on_change_start_pos_clicked(self, group_widget):
        self._hide_keypad(); self.start_button.setEnabled(False); self.active_group_for_editing = group_widget; self.edit_plate_fullscreen.emit(group_widget)
    def _set_active_input(self, display_widget):
        # If clicking outside input areas, hide keypad and clear styles
        if display_widget is None:
            self._hide_keypad()
            return
            
        # Reset to default style
        default_style = """
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
        """
        self.samples_display.setStyleSheet(default_style)
        for group in self.box_group_widgets:
            group.volume_display.setStyleSheet(default_style)
            
        # If clicking the same input, just reselect text
        if display_widget == self.active_input_display:
            if hasattr(display_widget, 'selectAll'):
                display_widget.selectAll()
            return
            
        # Set new active input
        self.active_input_display = display_widget
        
        # Highlight and focus with darker blue
        self.active_input_display.setStyleSheet("""
            QLineEdit {
                background-color: #005a9e;
                border: 3px solid #004578;
                border-radius: 8px;
                padding: 8px;
                color: white;
                font-family: Arial;
                font-size: 28pt;
                font-weight: bold;
            }
        """)
        self.active_input_display.setFocus()
        
        # Select all text
        if hasattr(self.active_input_display, 'selectAll'):
            self.active_input_display.selectAll()
        
        # Show and position keypad
        global_pos = self.active_input_display.mapToGlobal(QPoint(0, self.active_input_display.height()))
        self.keypad.move(global_pos.x(), global_pos.y() + 5)
        self.keypad.show()
        self.keypad.raise_()
    def _on_volume_display_clicked(self, group_widget):
        self.active_group_for_editing = group_widget; self._set_active_input(group_widget.volume_display)
    def _on_key_pressed(self, key):
        if not self.active_input_display:
            return
        
        # Get current text
        if self.active_input_display == self.samples_display:
            current_str = self.temp_sample_input
        else:
            current_str = self.active_input_display.text()
        current_str = str(current_str) if current_str else "0"
        
        # Handle key input
        if key == 'del':
            # Delete last character
            current_str = current_str[:-1] if current_str else "0"
        else:
            max_length = 3 if self.active_input_display == self.samples_display else 4
            # If the field is focused and all text is selected, replace it
            if hasattr(self.active_input_display, 'hasSelectedText') and self.active_input_display.hasSelectedText():
                current_str = key
            # Otherwise append if under length limit
            elif len(current_str) < max_length:
                if current_str == "0":  # Replace leading zero
                    current_str = key
                else:
                        current_str += key
        
        # Validate and update display
        if self.active_input_display == self.samples_display:
            # Validate sample count (1-96)
            value = int(current_str) if current_str else 0
            if value > 96:
                current_str = "96"
            # Store in temp variable but don't update plates yet
            self.temp_sample_input = current_str
            self.active_input_display.setText(current_str)
        
        # Update the display
        if self.active_input_display == self.samples_display:
            self.samples_input = current_str
            self.active_input_display.setText(current_str or "0")
            self._update_all_plates()
        else:
            self.active_input_display.setText(current_str or "0")
            if self.active_group_for_editing:
                self.active_group_for_editing.group_data['volume']['defaultValue'] = int(current_str or "0")
            self.active_input_display.setText(str(current_str or "0"))
    def _update_all_plates(self):
        try:
            # Check if this is a pooled script
            is_pooled = self.script_data.get("scriptType") == "pooled"
            
            # Update the actual sample input from temporary storage
            self.samples_input = self.temp_sample_input
            num_samples = int(self.samples_input or "0")
            
            # For pooled scripts, get sample data from journal
            sample_mapping = None
            if is_pooled:
                sample_mapping = self.journal_data.get_sample_mapping()
                if not sample_mapping:
                    print("No sample mapping available")
                    return
            
            # Validate sample range for standard scripts
            if not is_pooled:
                sample_range = self.script_data.get("sampleRange", {})
                min_s, max_s = sample_range.get("min", 1), sample_range.get("max", 96)
                
                if num_samples != 0 and not (min_s <= num_samples <= max_s):
                    QMessageBox.warning(self, "Ugyldig antall", f"Antall prøver må være mellom {min_s} og {max_s}.")
                    return
            
            # Update each box group
            for group in self.box_group_widgets:
                start_pos = group.group_data.get('currentStartPosition', 1)
                disabled = group.group_data.get('disabledWells', [])
                
                if is_pooled and sample_mapping and group.group_data.get("groupType") in ["individual", "pooled"]:
                    # Use specific sample data for pooled scripts
                    group_type = group.group_data.get("groupType")
                    group_samples = sample_mapping[group_type]
                    group.update_plates(len(group_samples), start_pos, disabled, group_samples)
                else:
                    # Standard script just uses the sample count
                    group.update_plates(num_samples, start_pos, disabled)
            
            # Update start button state based on samples and UDFs
            self._update_button_state()
        except (ValueError, AttributeError) as e: 
            print(f"Kunne ikke oppdatere plater: {e}")
    def _on_start_pipetting(self):
        try:
            import os
            from pathlib import Path
            
            # Create a function to ensure directories exist using Path
            def ensure_directory_exists(file_path):
                if not file_path:
                    print("Warning: Empty file path")
                    return False
                    
                try:
                    directory = os.path.dirname(file_path)
                    if not directory:
                        print(f"Warning: No directory in path: {file_path}")
                        return False
                        
                    # Use pathlib for more robust directory creation
                    path_obj = Path(directory)
                    if not path_obj.exists():
                        print(f"Creating directory: {directory}")
                        path_obj.mkdir(parents=True, exist_ok=True)
                        
                        # Verify directory was created
                        if path_obj.exists():
                            print(f"  Directory created successfully")
                            return True
                        else:
                            print(f"  Failed to create directory")
                            return False
                    return True
                except Exception as dir_err:
                    print(f"Error creating directory for {file_path}: {dir_err}")
                    return False
            
            print("\n--- Starting export process ---")
            
            # Pre-create critical directories
            critical_dirs = ["C:/robot/variables/Pooled"]
            for dir_path in critical_dirs:
                try:
                    dir_path_norm = os.path.normpath(dir_path)  # Normalize path format
                    print(f"Pre-creating critical directory: {dir_path_norm}")
                    Path(dir_path_norm).mkdir(parents=True, exist_ok=True)
                    if os.path.exists(dir_path_norm):
                        print(f"  Critical directory exists now: {dir_path_norm}")
                    else:
                        print(f"  WARNING: Failed to create directory: {dir_path_norm}")
                except Exception as dir_err:
                    print(f"  Error pre-creating directory {dir_path}: {dir_err}")
            
            # Handle visualization
            visualization_path = self.script_data.get("visualizationFile")
            if visualization_path:
                # Normalize path
                visualization_path = os.path.normpath(visualization_path)
                print(f"Saving visualization to: {visualization_path}")
                if ensure_directory_exists(visualization_path):
                    size = self.grab_container.size()
                    pixmap = QPixmap(size)
                    self.grab_container.render(pixmap)
                    pixmap.save(visualization_path)
                    print(f"Visualization saved successfully")
                else:
                    print(f"WARNING: Could not create directory for {visualization_path}")
            
            # Handle script target file
            if 'targetFile' in self.script_data:
                target_file = self.script_data['targetFile']
                # Normalize path
                target_file = os.path.normpath(target_file)
                print(f"Writing target file: {target_file}")
                if ensure_directory_exists(target_file):
                    with open(target_file, 'w') as f:
                        f.write(self.script_data['targetValue'])
                    print(f"Target file written successfully")
                else:
                    print(f"WARNING: Could not create directory for {target_file}")
            
            # Handle sample count file
            if 'sampleCountFile' in self.script_data and self.script_data['sampleCountFile']:
                sample_count_file = self.script_data['sampleCountFile']
                
                # Normalize the path to handle both formats of slashes
                sample_count_file = os.path.normpath(sample_count_file)
                
                print(f"Writing sample count file: {sample_count_file}")
                if ensure_directory_exists(sample_count_file):
                    with open(sample_count_file, 'w') as f:
                        f.write(self.samples_input or "0")
                    print(f"Sample count file written successfully")
                else:
                    print(f"WARNING: Could not create directory for {sample_count_file}")
            else:
                print("No sample count file specified, skipping")
            
            # Handle box groups
            print(f"Processing {len(self.box_group_widgets)} box groups")
            for i, group_widget in enumerate(self.box_group_widgets):
                group_data = group_widget.group_data
                print(f"Box group {i+1}: {group_data.get('groupName', 'Unnamed')}")
                
                # Write start position
                if 'startPositionFile' in group_data:
                    start_pos_file = group_data['startPositionFile']
                    # Normalize path
                    start_pos_file = os.path.normpath(start_pos_file)
                    print(f"  Writing start position to: {start_pos_file}")
                    if ensure_directory_exists(start_pos_file):
                        with open(start_pos_file, 'w') as f:
                            f.write(str(group_data['currentStartPosition']))
                        print(f"  Start position written successfully")
                    else:
                        print(f"  WARNING: Could not create directory for {start_pos_file}")
                
                # Write volume
                if 'volume' in group_data and 'volumeFile' in group_data['volume']:
                    volume_file = group_data['volume']['volumeFile']
                    # Normalize path
                    volume_file = os.path.normpath(volume_file)
                    print(f"  Writing volume to: {volume_file}")
                    if ensure_directory_exists(volume_file):
                        with open(volume_file, 'w') as f:
                            f.write(str(group_data['volume']['defaultValue']))
                        print(f"  Volume written successfully")
                    else:
                        print(f"  WARNING: Could not create directory for {volume_file}")
            
            # Handle user defined variables
            print(f"Processing {len(self.udf_widgets)} user defined variables")
            for i, udf_widget in enumerate(self.udf_widgets):
                if udf_widget["buttons"].checkedId() != -1:
                    selected_id = udf_widget["buttons"].checkedId()
                    selected_option = udf_widget["data"]["options"][selected_id]
                    if 'file' in selected_option:
                        udf_file = selected_option['file']
                        # Normalize path
                        udf_file = os.path.normpath(udf_file)
                        print(f"  UDF {i+1}: Writing to {udf_file}")
                        if ensure_directory_exists(udf_file):
                            with open(udf_file, 'w') as f:
                                f.write(str(selected_option['value']))
                        else:
                            print(f"  WARNING: Could not create directory for {udf_file}")
                        print(f"  UDF written successfully")
            
            # Save this script as the last run script in settings.json
            try:
                settings_path = self.base_dir / "settings.json"
                settings = {}
                if settings_path.exists():
                    with open(settings_path, 'r') as f:
                        try:
                            settings = json.load(f)
                        except json.JSONDecodeError:
                            pass
                
                # Construct config path
                if 'folder_name' in self.script_data:
                    config_path = self.base_dir / "scripts" / self.script_data['folder_name'] / "config.json"
                    settings['last_script_config'] = str(config_path)
                    
                    with open(settings_path, 'w') as f:
                        json.dump(settings, f, indent=4)
                        print(f"Saved last run script config to settings: {config_path}")
            except Exception as e:
                print(f"Could not save last run script setting: {e}")
            
            print("All files written successfully!")
            print("Configuration saved. Closing GUI.")
            QApplication.instance().quit()
            
            print("Konfigurasjon lagret. Lukker GUI."); QApplication.instance().quit()
        except Exception as e:
            import traceback
            import sys
            error_details = traceback.format_exc()
            print(f"ERROR: Failed to save configuration")
            print(f"Exception type: {type(e).__name__}")
            print(f"Exception message: {str(e)}")
            print(f"Error details: {error_details}")
            
            # Check for common error causes
            if "No such file or directory" in str(e):
                print("Checking directories:")
                for path in [self.script_data.get('visualizationFile', ''), 
                            self.script_data.get('targetFile', ''),
                            self.script_data.get('sampleCountFile', '')]:
                    if path:
                        dir_path = os.path.dirname(path)
                        print(f"  Directory for {path}: exists={os.path.exists(dir_path)}, is_dir={os.path.isdir(dir_path) if os.path.exists(dir_path) else 'N/A'}")
                        
                # Try creating the directory with different method
                try:
                    from pathlib import Path
                    problem_path = str(e).split("No such file or directory: ")[-1].strip("'\"")
                    print(f"Trying to create directory for problematic path: {problem_path}")
                    Path(os.path.dirname(problem_path)).mkdir(parents=True, exist_ok=True)
                    print(f"Directory created successfully with Path")
                except Exception as dir_e:
                    print(f"Failed to create directory with alternative method: {dir_e}")
            
            QMessageBox.critical(self, "Feil ved lagring", f"En feil oppstod under skriving til fil:\n{e}")

# ... (Resten av filen, SettingsScreen, GeneratorScreen, etc. er uendret)
class SettingsScreen(QWidget):
    back_to_menu = Signal(); open_generator = Signal(); open_generator_for_edit = Signal(dict)
    def __init__(self, base_dir, parent=None):
        super().__init__(parent); self.base_dir = base_dir; self.settings_file = "settings.json"; self._load_settings(); main_layout = QVBoxLayout(self); scroll_area = QScrollArea(); scroll_area.setWidgetResizable(True); container = QWidget(); scroll_layout = QVBoxLayout(container); scroll_area.setWidget(container); main_layout.addWidget(scroll_area); top_bar_layout = QHBoxLayout(); back_button = QPushButton("← Tilbake til menyen"); back_button.setMinimumHeight(80); back_button.setFont(QFont("Arial", 20)); back_button.clicked.connect(self.back_to_menu.emit); top_bar_layout.addWidget(back_button, alignment=Qt.AlignLeft); top_bar_layout.addStretch(1); title = QLabel("Innstillinger"); title.setFont(QFont("Arial", 48, QFont.Bold)); visibility_label = QLabel("Administrer Scripts"); visibility_label.setFont(QFont("Arial", 28, QFont.Bold)); self.scripts_list_layout = QVBoxLayout(); tools_label = QLabel("Verktøy"); tools_label.setFont(QFont("Arial", 28, QFont.Bold)); generator_button = QPushButton("Opprett nytt script"); generator_button.setFont(QFont("Arial", 24)); generator_button.setMinimumSize(500, 100); generator_button.clicked.connect(self.open_generator.emit); cleanup_button = QPushButton("Rydd i scripts"); cleanup_button.setFont(QFont("Arial", 24)); cleanup_button.setMinimumSize(500, 100); cleanup_button.clicked.connect(self._run_cleanup_script); scroll_layout.addLayout(top_bar_layout); scroll_layout.addWidget(title, alignment=Qt.AlignCenter); scroll_layout.addWidget(visibility_label); scroll_layout.addLayout(self.scripts_list_layout); scroll_layout.addSpacing(50); scroll_layout.addWidget(tools_label); scroll_layout.addWidget(generator_button, alignment=Qt.AlignCenter); scroll_layout.addWidget(cleanup_button, alignment=Qt.AlignCenter); scroll_layout.addStretch(1)
    def _load_settings(self):
        try:
            with open(self.settings_file, 'r') as f: self.settings = json.load(f)
        except FileNotFoundError: self.settings = {"inactive_scripts": []}
    def _save_settings(self):
        with open(self.settings_file, 'w') as f: json.dump(self.settings, f, indent=2)
    def populate_scripts_list(self):
        while self.scripts_list_layout.count():
            child = self.scripts_list_layout.takeAt(0);
            if child.widget(): child.widget().deleteLater()
        inactive_scripts = self.settings.get("inactive_scripts", []); scripts_path = self.base_dir / "scripts"
        for dir_name in sorted(os.listdir(scripts_path)):
            if os.path.isdir(os.path.join(scripts_path, dir_name)):
                row_layout = QHBoxLayout(); checkbox = QCheckBox(); checkbox.setChecked(dir_name not in inactive_scripts); checkbox.stateChanged.connect(lambda state, name=dir_name: self._on_checkbox_change(state, name)); name_label = QLabel(dir_name); name_label.setFont(QFont("Arial", 20)); edit_button = QPushButton("Endre"); edit_button.setFont(QFont("Arial", 16)); edit_button.clicked.connect(lambda checked=False, name=dir_name: self._edit_script(name)); delete_button = QPushButton("Slett"); delete_button.setFont(QFont("Arial", 16)); delete_button.clicked.connect(lambda checked=False, name=dir_name: self._delete_script(name)); row_layout.addWidget(checkbox); row_layout.addWidget(name_label, 1); row_layout.addWidget(edit_button); row_layout.addWidget(delete_button); self.scripts_list_layout.addLayout(row_layout)
    def _on_checkbox_change(self, state, script_name):
        inactive_scripts = self.settings.get("inactive_scripts", []); is_checked = (state == Qt.CheckState.Checked.value)
        if is_checked and script_name in inactive_scripts: inactive_scripts.remove(script_name)
        elif not is_checked and script_name not in inactive_scripts: inactive_scripts.append(script_name)
        self.settings["inactive_scripts"] = inactive_scripts; self._save_settings()
    def _run_cleanup_script(self):
        script_path = self.base_dir / "rydd.vbs"; print(f"Kjører eksternt script: {script_path}...")
        try:
            subprocess.Popen(["wscript", str(script_path)]); print("Script startet.")
        except Exception as e: print(f"En feil oppstod under kjøring av script: {e}")
    def _edit_script(self, script_name):
        config_path = self.base_dir / "scripts" / script_name / "config.json"
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                script_data = json.load(f); script_data['folder_name'] = script_name; self.open_generator_for_edit.emit(script_data)
        except Exception as e: QMessageBox.critical(self, "Feil", f"Kunne ikke laste script for redigering:\n{e}")
    def _delete_script(self, script_name):
        reply = QMessageBox.question(self, "Bekreft sletting", f"Er du sikker på at du vil slette scriptet '{script_name}' permanent?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                shutil.rmtree(self.base_dir / "scripts" / script_name); QMessageBox.information(self, "Suksess", f"Scriptet '{script_name}' ble slettet."); self.populate_scripts_list()
            except Exception as e: QMessageBox.critical(self, "Feil", f"Kunne ikke slette mappen:\n{e}")

class BoxGroupForm(QFrame):
    remove_me = Signal(object)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QFormLayout(self)
        font = QFont("Arial", 14)
        
        # Initialize all input fields
        self.group_name_input = QLineEdit()
        self.labware_name_input = QLineEdit()  # New field for Labware Name
        self.shape_input = QComboBox()
        self.shape_input.addItems(["circle", "rect"])
        self.max_boxes_input = QLineEdit("1")
        self.start_pos_input = QLineEdit("1")
        self.disabled_wells_input = QLineEdit()
        self.vol_default_input = QLineEdit("500")
        self.start_pos_file_input = QLineEdit()
        self.volume_file_input = QLineEdit()
        self.color_input = QComboBox()
        
        # Add group type selector for pooled scripts
        self.type_input = QComboBox()
        self.type_input.addItems(["standard", "individual", "pooled"])
        self.type_input.setCurrentText("standard")
        
        # Add standard colors with friendly names
        self.color_options = {
            "Grå": "#808080",
            "Hvit": "#FFFFFF",
            "Svart": "#000000",
            "Rød": "#FF0000",
            "Oransje": "#FFA500",
            "Gul": "#FFD700",
            "Grønn": "#008000",
            "Blå": "#0000FF",
            "Indigo": "#4B0082",
            "Fiolett": "#8A2BE2",
            "Rosa": "#FF69B4",
            "Brun": "#8B4513"
        }
        
        self.color_input.addItems(self.color_options.keys())
        self.color_input.setCurrentText("Grå")  # Default color
        
        remove_button = QPushButton("X Fjern")
        remove_button.setStyleSheet("color: red;")
        remove_button.clicked.connect(lambda: self.remove_me.emit(self))
        # Set font for all widgets
        for w in [self.group_name_input, self.labware_name_input, self.shape_input, self.max_boxes_input, 
                 self.start_pos_input, self.disabled_wells_input, self.vol_default_input, 
                 self.start_pos_file_input, self.volume_file_input, self.color_input, remove_button]:
            w.setFont(font)
            
        # Add rows to form
        layout.addRow(remove_button)
        layout.addRow("Gruppenavn:", self.group_name_input)
        layout.addRow("Labware Navn (for QC):", self.labware_name_input)
        layout.addRow("Type:", self.type_input)
        layout.addRow("Brønnform:", self.shape_input)
        layout.addRow("Boksens farge:", self.color_input)  # New color selector
        layout.addRow("Maks antall bokser:", self.max_boxes_input)
        layout.addRow("Initiell startposisjon:", self.start_pos_input)
        layout.addRow("Deaktiverte brønner:", self.disabled_wells_input)
        layout.addRow("Standard volum (µL):", self.vol_default_input)
        layout.addRow("Fil for startposisjon:", make_path_picker(self, self.start_pos_file_input, mode="save", caption="Velg fil for startposisjon", file_filter="Tekstfiler (*.txt);;Alle filer (*)"))
        layout.addRow("Fil for volum:", make_path_picker(self, self.volume_file_input, mode="save", caption="Velg fil for volum", file_filter="Tekstfiler (*.txt);;Alle filer (*)"))
    def get_data(self):
        try:
            disabled_wells = [int(x.strip()) for x in self.disabled_wells_input.text().split(',') if x.strip()]
        except ValueError:
            return None
        return {
            "groupName": self.group_name_input.text() or "Boks Gruppe",
            "labwareName": self.labware_name_input.text(),
            "groupType": self.type_input.currentText(),
            "shape": self.shape_input.currentText(),
            "color": self.color_options[self.color_input.currentText()],
            "maxBoxes": int(self.max_boxes_input.text() or "1"),
            "startPositionFile": self.start_pos_file_input.text(),
            "initialStartPosition": int(self.start_pos_input.text() or "1"),
            "disabledWells": disabled_wells,
            "volume": {
                "volumeFile": self.volume_file_input.text(),
                "defaultValue": int(self.vol_default_input.text() or "0"),
                "min": 0,
                "max": 5000
            }
        }
        
    def set_data(self, data):
        self.group_name_input.setText(data.get("groupName", ""))
        self.labware_name_input.setText(data.get("labwareName", ""))
        
        # Only set type if it's in the available items
        requested_type = data.get("groupType", "standard")
        available_types = [self.type_input.itemText(i) for i in range(self.type_input.count())]
        if requested_type in available_types:
            self.type_input.setCurrentText(requested_type)
        
        self.shape_input.setCurrentText(data.get("shape", "rect"))
        
        # Set color if present, otherwise default to gray
        if "color" in data:
            color_hex = data["color"]
            color_name = next((name for name, hex in self.color_options.items() 
                             if hex.lower() == color_hex.lower()), "Grå")
            self.color_input.setCurrentText(color_name)
            
        self.max_boxes_input.setText(str(data.get("maxBoxes", 1)))
        self.start_pos_input.setText(str(data.get("initialStartPosition", 1)))
        self.start_pos_file_input.setText(data.get("startPositionFile", ""))
        disabled_str = ", ".join(map(str, data.get("disabledWells", [])))
        self.disabled_wells_input.setText(disabled_str)
        volume = data.get("volume", {})
        self.vol_default_input.setText(str(volume.get("defaultValue", 0)))
        self.volume_file_input.setText(volume.get("volumeFile", ""))

class UDFOptionForm(QWidget):
    remove_me = Signal(object)
    def __init__(self, parent=None):
        super().__init__(parent)
        font = QFont("Arial", 14)
        layout = QHBoxLayout(self)
        self.label_input = QLineEdit()
        self.value_input = QLineEdit()
        self.file_input = QLineEdit()
        remove_button = QPushButton("x")
        remove_button.setFixedSize(30, 30)
        for w in [self.label_input, self.value_input, self.file_input, remove_button]:
            w.setFont(font)

        layout.addWidget(QLabel("Tekst:"))
        layout.addWidget(self.label_input, 1)
        layout.addWidget(QLabel("Verdi:"))
        layout.addWidget(self.value_input, 1)
        layout.addWidget(QLabel("Filsti:"))
        layout.addWidget(make_path_picker(self, self.file_input, mode="save", caption="Velg filsti", file_filter="Tekstfiler (*.txt);;Alle filer (*)"), 2)
        layout.addWidget(remove_button)
        remove_button.clicked.connect(lambda: self.remove_me.emit(self))
    def get_data(self):
        return {"label": self.label_input.text(), "value": self.value_input.text(), "file": self.file_input.text()}
    def set_data(self, data):
        self.label_input.setText(data.get("label", "")); self.value_input.setText(str(data.get("value", ""))); self.file_input.setText(data.get("file", ""))

class UDFForm(QFrame):
    remove_me = Signal(object)
    def __init__(self, parent=None):
        super().__init__(parent); self.setFrameShape(QFrame.Shape.StyledPanel); self.option_forms = []; layout = QVBoxLayout(self); font = QFont("Arial", 14); self.question_input = QLineEdit(); self.question_input.setFont(font)
        remove_button = QPushButton("X Fjern Variabel"); remove_button.setStyleSheet("color: red;"); remove_button.clicked.connect(lambda: self.remove_me.emit(self))
        self.options_layout = QVBoxLayout(); add_option_button = QPushButton("+ Legg til valg"); add_option_button.setFont(font); add_option_button.clicked.connect(lambda: self._add_option_form())
        layout.addWidget(remove_button); layout.addWidget(QLabel("Spørsmål:")); layout.addWidget(self.question_input); layout.addLayout(self.options_layout); layout.addWidget(add_option_button)
    def _add_option_form(self, data=None):
        form = UDFOptionForm(); form.remove_me.connect(self._remove_option_form)
        if data: form.set_data(data)
        self.options_layout.addWidget(form); self.option_forms.append(form)
    def _remove_option_form(self, form):
        self.options_layout.removeWidget(form); self.option_forms.remove(form); form.deleteLater()
    def get_data(self):
        if not self.question_input.text(): return None
        options = []
        for form in self.option_forms:
            data = form.get_data()
            if data and data['label']: options.append(data)
        return {"question": self.question_input.text(), "options": options} if options else None
    def set_data(self, data):
        self.question_input.setText(data.get("question", "")); 
        for opt_data in data.get("options", []): self._add_option_form(opt_data)

class GeneratorScreen(QWidget):
    back_to_settings = Signal()
    def __init__(self, scripts_dir, parent=None):
        super().__init__(parent)
        self.scripts_dir = scripts_dir
        self.editing_folder_name = None
        self.box_group_forms = []
        self.udf_forms = []
        self.is_loading_existing = False  # Flag to prevent automatic box group creation when loading existing scripts
        main_layout = QVBoxLayout(self); scroll_area = QScrollArea(); scroll_area.setWidgetResizable(True); main_layout.addWidget(scroll_area); container = QWidget(); form_layout = QFormLayout(container); form_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows); scroll_area.setWidget(container); font = QFont("Arial", 16)
        # Create main input fields
        # Create script type selector
        self.script_type_input = QComboBox()
        self.script_type_input.addItems(["standard", "pooled"])
        
        # Create main input fields
        self.script_name_input = QLineEdit()
        self.target_value_input = QLineEdit()
        self.description_input = QTextEdit()
        self.thumbnail_input = QLineEdit()
        self.target_file_input = QLineEdit("C:/robot/selected_script.txt")
        self.visualization_file_input = QLineEdit("script_visual.png")
        
        # Create sample range widget
        self.sample_range_widget = QWidget()
        sample_range_layout = QHBoxLayout(self.sample_range_widget)
        self.sample_min_input = QLineEdit("1")
        self.sample_max_input = QLineEdit("96")
        sample_range_layout.addWidget(self.sample_min_input)
        sample_range_layout.addWidget(QLabel("til"))
        sample_range_layout.addWidget(self.sample_max_input)
        
        # Create file inputs
        self.sample_count_file_input = QLineEdit("C:/robot/variables/sample_count.txt")
        self.journal_dir_input = QLineEdit()
        self.journal_dir_input.setPlaceholderText("Eksempel: test_data.txt")
        
        # Create source layout input
        self.source_layout_input = QLineEdit("8x12")
        self.source_layout_input.setPlaceholderText("F.eks. 8x12 eller 4x6")
        
        # Create box groups layout
        self.box_groups_layout = QVBoxLayout()
        
        # Connect script type change handler after all widgets are created
        self.script_type_input.currentTextChanged.connect(self._on_script_type_changed)
        
        for w in [self.script_name_input, self.target_value_input, self.description_input, self.thumbnail_input, 
                 self.sample_min_input, self.sample_max_input, self.target_file_input, self.sample_count_file_input, 
                 self.visualization_file_input, self.script_type_input, self.journal_dir_input, self.source_layout_input]: w.setFont(font)
        # General info section
        form_layout.addRow(QLabel("<h3>Generell Info</h3>"))
        form_layout.addRow("Navn på script:", self.script_name_input)
        form_layout.addRow("Type script:", self.script_type_input)
        form_layout.addRow("Verdi for robot:", self.target_value_input)
        form_layout.addRow("Beskrivelse:", self.description_input)
        form_layout.addRow("Filnavn for thumbnail:", make_path_picker(self, self.thumbnail_input, mode="open", caption="Velg thumbnail", file_filter="Bilder (*.png *.jpg *.jpeg *.bmp);;Alle filer (*)"))
        form_layout.addRow("Kilde-layout (RxC):", self.source_layout_input)
        
        # Sample configuration section
        form_layout.addRow("Antall prøver (min-maks):", self.sample_range_widget)
        
        # File paths section
        form_layout.addRow(QLabel("<u>Globale filstier:</u>"))
        form_layout.addRow("Fil for valgt script:", make_path_picker(self, self.target_file_input, mode="save", caption="Velg fil for valgt script", file_filter="Tekstfiler (*.txt);;Alle filer (*)"))
        form_layout.addRow("Fil for antall prøver:", make_path_picker(self, self.sample_count_file_input, mode="save", caption="Velg fil for antall prøver", file_filter="Tekstfiler (*.txt);;Alle filer (*)"))
        form_layout.addRow("Fil for visualisering (.png):", make_path_picker(self, self.visualization_file_input, mode="save", caption="Velg fil for visualisering", file_filter="Bilder (*.png);;Alle filer (*)"))
        form_layout.addRow("Journaldatafil:", make_path_picker(self, self.journal_dir_input, mode="open", caption="Velg journaldata", file_filter="Datafiler (*.txt *.csv);;Alle filer (*)"))
        
        # Initialize visibility
        self._on_script_type_changed(self.script_type_input.currentText())
        form_layout.addRow(QLabel("<h3>Boksgrupper</h3>")); self.box_groups_layout = QVBoxLayout(); form_layout.addRow(self.box_groups_layout); add_group_button = QPushButton("+ Legg til boksgruppe"); add_group_button.setFont(font); add_group_button.clicked.connect(lambda: self._add_box_group_form()); form_layout.addRow(add_group_button)
        form_layout.addRow(QLabel("<h3>Brukerdefinerte valg</h3>")); self.udf_layout = QVBoxLayout(); form_layout.addRow(self.udf_layout); add_udf_button = QPushButton("+ Legg til brukerdefinert valg"); add_udf_button.setFont(font); add_udf_button.clicked.connect(lambda: self._add_udf_form()); form_layout.addRow(add_udf_button)
        back_button = QPushButton("← Avbryt"); back_button.setFont(font); back_button.clicked.connect(self.back_to_settings.emit); save_button = QPushButton("Lagre Script"); save_button.setFont(font); save_button.clicked.connect(self._save_script); button_layout = QHBoxLayout(); button_layout.addWidget(back_button); button_layout.addStretch(1); button_layout.addWidget(save_button); main_layout.addLayout(button_layout)
    def _add_box_group_form(self, data=None):
        form = BoxGroupForm()
        form.remove_me.connect(self._remove_box_group_form)
        
        # Set up type options based on current script type
        is_pooled = self.script_type_input.currentText() == "pooled"
        form.type_input.clear()
        
        if is_pooled:
            form.type_input.addItems(["individual", "pooled"])
            form.type_input.setCurrentText("individual")  # Default for new box groups in pooled scripts
        else:
            form.type_input.addItems(["standard"])
            form.type_input.setCurrentText("standard")
            
        # Apply data if provided
        if data: 
            form.set_data(data)
            
        self.box_groups_layout.addWidget(form)
        self.box_group_forms.append(form)
    def _remove_box_group_form(self, form):
        if len(self.box_group_forms) > 1: self.box_groups_layout.removeWidget(form); self.box_group_forms.remove(form); form.deleteLater()
        else: QMessageBox.warning(self, "Feil", "Et script må ha minst én boksgruppe.")
    def _add_udf_form(self, data=None):
        form = UDFForm(); form.remove_me.connect(self._remove_udf_form);
        if data: form.set_data(data)
        self.udf_layout.addWidget(form); self.udf_forms.append(form)
    def _remove_udf_form(self, form):
        self.udf_layout.removeWidget(form); self.udf_forms.remove(form); form.deleteLater()
    def _clear_forms(self):
        while self.box_group_forms:
            form = self.box_group_forms[0]; self.box_groups_layout.removeWidget(form); self.box_group_forms.remove(form); form.deleteLater()
        while self.udf_forms:
            form = self.udf_forms[0]; self.udf_layout.removeWidget(form); self.udf_forms.remove(form); form.deleteLater()
    def _on_script_type_changed(self, script_type):
        # Show/hide fields based on script type
        is_pooled = script_type == "pooled"
        
        # Control visibility of fields
        self.journal_dir_input.setVisible(is_pooled)
        self.sample_count_file_input.setVisible(not is_pooled)
        self.sample_range_widget.setVisible(not is_pooled)
        
        # Check if we're loading an existing script - if so, don't automatically add box groups
        if self.is_loading_existing:
            # Just update type selectors for existing box groups
            for form in self.box_group_forms:
                form.type_input.clear()
                if is_pooled:
                    form.type_input.addItems(["individual", "pooled"])
                    # Try to preserve the existing type if possible
                    current_type = form.get_data().get("groupType", "")
                    if current_type in ["individual", "pooled"]:
                        form.type_input.setCurrentText(current_type)
                    else:
                        form.type_input.setCurrentText("individual")
                else:
                    form.type_input.addItems(["standard"])
                    form.type_input.setCurrentText("standard")
            return
        
        # Clear any existing box groups for new scripts
        self._clear_forms()
        
        # Add default box groups based on script type for new scripts
        if is_pooled:
            # Add individual samples group
            individual_group = {
                "groupName": "Individuelle Prøver",
                "groupType": "individual",
                "shape": "rect",
                "color": "#0078d4"
            }
            self._add_box_group_form(individual_group)
            
            # Add pooled samples group
            pooled_group = {
                "groupName": "Poolede Prøver",
                "groupType": "pooled",
                "shape": "rect",
                "color": "#00b347"
            }
            self._add_box_group_form(pooled_group)
            
            # Show type selector with only individual and pooled options
            for form in self.box_group_forms:
                form.type_input.clear()
                form.type_input.addItems(["individual", "pooled"])
                if "individual" in form.group_name_input.text().lower():
                    form.type_input.setCurrentText("individual")
                else:
                    form.type_input.setCurrentText("pooled")
                form.type_input.setVisible(True)
        else:
            # Add a standard box group
            self._add_box_group_form()
            
            # Show type selector with only standard option for standard scripts
            for form in self.box_group_forms:
                form.type_input.clear()
                form.type_input.addItems(["standard"])
                form.type_input.setCurrentText("standard")
                form.type_input.setVisible(True)

    def reset_form(self):
        # Make sure we're not in "loading existing" mode
        self.is_loading_existing = False
        
        # Clear existing forms and reset fields
        self._clear_forms()
        self.editing_folder_name = None
        self.script_name_input.clear()
        self.script_type_input.setCurrentText("standard")
        self.target_value_input.clear()
        self.description_input.clear()
        self.thumbnail_input.clear()
        self.sample_min_input.setText("1")
        self.sample_max_input.setText("96")
        self.target_file_input.setText("C:/robot/selected_script.txt")
        self.sample_count_file_input.setText("C:/robot/variables/sample_count.txt")
        self.visualization_file_input.setText("script_visual.png")
        self.journal_dir_input.clear()
        self.journal_dir_input.setVisible(False)
        self.source_layout_input.setText("8x12")
        self._add_box_group_form()
    def load_data_for_edit(self, script_data):
        # Set a flag to prevent automatic box group creation during type change
        self.is_loading_existing = True
        
        # Clear existing forms
        self._clear_forms()
        
        # Set basic script data
        self.editing_folder_name = script_data.get('folder_name')
        self.script_name_input.setText(script_data.get("scriptName"))
        self.target_value_input.setText(script_data.get("targetValue", ""))
        self.description_input.setText(script_data.get("description", ""))
        self.thumbnail_input.setText(script_data.get("thumbnail", ""))
        self.target_file_input.setText(script_data.get("targetFile", ""))
        self.sample_count_file_input.setText(script_data.get("sampleCountFile", ""))
        self.visualization_file_input.setText(script_data.get("visualizationFile", "script_visual.png"))
        self.journal_dir_input.setText(script_data.get("journalDataFile", ""))
        self.source_layout_input.setText(script_data.get("sourceLayout", "8x12"))
        
        # Set script type (this will trigger _on_script_type_changed)
        self.script_type_input.setCurrentText(script_data.get("scriptType", "standard"))
        
        # Set sample range
        sample_range = script_data.get("sampleRange", {})
        self.sample_min_input.setText(str(sample_range.get("min", 1)))
        self.sample_max_input.setText(str(sample_range.get("max", 96)))
        
        # Add existing box groups from the script data
        for group_data in script_data.get("boxGroups", []): 
            self._add_box_group_form(group_data)
            
        # Add existing UDFs from the script data
        for udf_data in script_data.get("userDefinedVariables", []): 
            self._add_udf_form(udf_data)
            
        # Reset the flag after loading
        self.is_loading_existing = False
    def _save_script(self):
        script_name = self.script_name_input.text().strip();
        if not script_name: QMessageBox.warning(self, "Feil", "Navn på script kan ikke være tomt."); return
        folder_name = self.editing_folder_name if self.editing_folder_name else re.sub(r'[-\s]+', '_', re.sub(r'[^\w\s-]', '', script_name.lower()).strip())
        box_groups_data = [];
        for form in self.box_group_forms:
            data = form.get_data()
            if data is None: QMessageBox.warning(self, "Feil", "Deaktiverte brønner må være en liste med tall."); return
            box_groups_data.append(data)
        udf_data = [form.get_data() for form in self.udf_forms if form.get_data()]
        config_data = {
            "scriptName": script_name,
            "scriptType": self.script_type_input.currentText(),
            "description": self.description_input.toPlainText(),
            "thumbnail": self.thumbnail_input.text(),
            "visualizationFile": self.visualization_file_input.text(),
            "targetFile": self.target_file_input.text(),
            "targetValue": self.target_value_input.text(),
            "sampleCountFile": self.sample_count_file_input.text(),
            "sampleRange": {
                "min": int(self.sample_min_input.text() or 1),
                "max": int(self.sample_max_input.text() or 96)
            },
            "sourceLayout": self.source_layout_input.text(),
            "boxGroups": box_groups_data,
            "userDefinedVariables": udf_data
        }
        
        # Add journal data file path for pooled scripts
        if self.script_type_input.currentText() == "pooled":
            journal_path = self.journal_dir_input.text().strip()
            if not journal_path:
                QMessageBox.warning(self, "Mangler journaldata", 
                                  "Vennligst spesifiser mappe for journaldata.")
                return
            config_data["journalDataFile"] = journal_path
        try:
            script_folder_path = self.scripts_dir / folder_name; os.makedirs(script_folder_path, exist_ok=True)
            with open(script_folder_path / "config.json", 'w', encoding='utf-8') as f: json.dump(config_data, f, indent=4)
            QMessageBox.information(self, "Suksess", f"Scriptet '{script_name}' ble lagret!"); self.back_to_settings.emit()
        except Exception as e: QMessageBox.critical(self, "Feil", f"Kunne ikke lagre script:\n{e}")