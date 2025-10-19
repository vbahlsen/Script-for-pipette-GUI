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
                               QTextEdit, QRadioButton, QButtonGroup, QGroupBox, QGridLayout)
from PySide6.QtCore import Signal, Qt, QPoint
from PySide6.QtGui import QFont, QIntValidator, QPixmap, QPainter, QColor
from PySide6.QtWidgets import QApplication

from gui_widgets import WellPlateWidget, NumericKeypad, ThumbnailButton

class ScriptSelectorScreen(QWidget):
    script_selected = Signal(dict); settings_clicked = Signal()
    def __init__(self, base_dir, parent=None):
        super().__init__(parent); self.base_dir = base_dir; self.scripts_dir = base_dir / "scripts"; self.main_layout = QVBoxLayout(self); title = QLabel("Velg script"); title.setFont(QFont("Arial", 48, QFont.Bold)); self.main_layout.addWidget(title, alignment=Qt.AlignCenter); scroll_area = QScrollArea(); scroll_area.setWidgetResizable(True); scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff); scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded); self.button_container = QWidget(); self.button_layout = QGridLayout(self.button_container); self.button_layout.setSpacing(20); self.button_layout.setAlignment(Qt.AlignTop | Qt.AlignCenter); scroll_area.setWidget(self.button_container); self.main_layout.addWidget(scroll_area, 1); bottom_bar_layout = QHBoxLayout(); settings_button = QPushButton("⚙️"); settings_button.setFont(QFont("Arial", 30)); settings_button.setFixedSize(80, 80); settings_button.clicked.connect(self.settings_clicked.emit); bottom_bar_layout.addStretch(1); bottom_bar_layout.addWidget(settings_button); self.main_layout.addLayout(bottom_bar_layout)
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
        cols = 4
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
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._setup_ui()
        self.update_displays()
    
    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        name_label = QLabel(self.group_data.get("groupName", "Boksgruppe"))
        name_label.setFont(QFont("Arial", 28, QFont.Bold))
        name_label.setAlignment(Qt.AlignCenter)
        
        # FIKS: Overflødig start_pos_display er fjernet herfra.
        
        controls_layout = QVBoxLayout()
        self._setup_controls(controls_layout)

        self.plates_container = QWidget()
        self.plates_layout = QVBoxLayout(self.plates_container)
        
        main_layout.addWidget(name_label)
        main_layout.addLayout(controls_layout)
        main_layout.addWidget(self.plates_container, stretch=1)

    def _setup_controls(self, layout):
        volume_layout = QHBoxLayout()
        volume_label = QLabel("Volum (µL):")
        volume_label.setFont(QFont("Arial", 20))
        self.volume_display = QPushButton()
        self.volume_display.setFont(QFont("Arial", 20, QFont.Bold))
        self.volume_display.setMinimumWidth(120)
        volume_layout.addWidget(volume_label)
        volume_layout.addWidget(self.volume_display)
        volume_layout.addStretch(1)
        
        button_layout = QHBoxLayout()
        self.change_pos_button = QPushButton("Endre startposisjon")
        self.change_pos_button.setFont(QFont("Arial", 20))
        button_layout.addStretch(1)
        button_layout.addWidget(self.change_pos_button)
        button_layout.addStretch(1)

        layout.addLayout(volume_layout)
        layout.addLayout(button_layout)
        
        self.volume_display.clicked.connect(lambda: self.volume_display_clicked.emit(self))
        self.change_pos_button.clicked.connect(lambda: self.change_start_pos_clicked.emit(self))

    def update_displays(self):
        volume = self.group_data.get('volume', {}).get('defaultValue', 0)
        self.volume_display.setText(str(volume))
        for plate in self.plate_widgets:
            plate.start_pos = self.group_data.get('currentStartPosition', 1)
            plate.update()

    def update_plates(self, sample_count, start_pos, disabled_wells):
        while self.plates_layout.count():
            child = self.plates_layout.takeAt(0)
            if child.widget(): child.widget().deleteLater()
        self.plate_widgets.clear()

        show_title_on_first_plate = True
        
        if sample_count <= 0:
            plate = WellPlateWidget(shape=self.group_data.get("shape", "rect"), show_title=show_title_on_first_plate)
            plate.set_state(start_pos=start_pos, sample_count=0, disabled_wells=disabled_wells)
            self.plates_layout.addWidget(plate)
            self.plate_widgets.append(plate)
            return

        samples_to_distribute = sample_count
        num_plates_to_show = self.group_data.get("maxBoxes", 1)
        current_pos_on_plate = start_pos
        
        for i in range(num_plates_to_show):
            if samples_to_distribute <= 0:
                break

            show_title = (i == 0)
            plate = WellPlateWidget(shape=self.group_data.get("shape", "rect"), show_title=show_title)

            available_wells_on_this_plate = 0
            for well in range(current_pos_on_plate, 97):
                if well not in disabled_wells:
                    available_wells_on_this_plate += 1
            
            samples_on_this_plate = min(samples_to_distribute, available_wells_on_this_plate)
            
            plate.set_state(start_pos=current_pos_on_plate, sample_count=samples_on_this_plate, disabled_wells=disabled_wells)
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
        super().__init__(parent); self.base_dir = base_dir; self.box_group_widgets = []; self.active_group_for_editing = None; self.udf_widgets = []; self._setup_ui(QVBoxLayout(self)); self._connect_signals()
    def load_script_data(self, script_data):
        self.keypad.hide(); self.script_data = script_data
        while self.groups_layout.count():
            child = self.groups_layout.takeAt(0)
            if child.widget(): child.widget().deleteLater()
        self.box_group_widgets.clear()
        for group_data in self.script_data.get("boxGroups", []):
            try:
                with open(group_data['startPositionFile'], 'r') as f:
                    pos_from_file = int(f.read().strip())
                    if 1 <= pos_from_file <= 96: group_data['currentStartPosition'] = pos_from_file
                    else: group_data['currentStartPosition'] = group_data['initialStartPosition']
            except (FileNotFoundError, ValueError, KeyError): group_data['currentStartPosition'] = group_data['initialStartPosition']
            group_widget = BoxGroupWidget(group_data); group_widget.volume_display_clicked.connect(self._on_volume_display_clicked); group_widget.change_start_pos_clicked.connect(self._on_change_start_pos_clicked); 
            self.groups_layout.addWidget(group_widget); self.box_group_widgets.append(group_widget)
        self.samples_input = ""; self.samples_display.setText("0"); self.start_button.setEnabled(False); self._set_active_input(None); self.script_name_label.setText(self.script_data.get("scriptName", "Ukjent Script"))
        self.description_label.setText(self.script_data.get("description", "")); sample_range = self.script_data.get("sampleRange", {}); min_s, max_s = sample_range.get("min", 1), sample_range.get("max", 96); self.sample_range_label.setText(f"Gyldig antall: {min_s} - {max_s}")
        self.thumbnail_label.clear(); thumbnail_path = script_data.get("thumbnail", "")
        if thumbnail_path:
            full_path = self.base_dir / "scripts" / script_data['folder_name'] / thumbnail_path
            if os.path.exists(full_path):
                pixmap = QPixmap(str(full_path)); self.thumbnail_label.setPixmap(pixmap)
            else: self.thumbnail_label.setText("Bilde\nikke\nfunnet")
        for udf_widget in self.udf_widgets: udf_widget["group"].deleteLater()
        self.udf_widgets.clear()
        udf_list = self.script_data.get("userDefinedVariables", [])
        for udf_data in udf_list:
            if udf_data and udf_data.get("question"):
                group_box = QGroupBox(udf_data.get("question")); group_box.setFont(QFont("Arial", 18)); layout = QVBoxLayout(group_box); button_group = QButtonGroup(self)
                for i, option in enumerate(udf_data.get("options", [])):
                    if option.get("label"):
                        radio = QRadioButton(option.get("label")); radio.setFont(QFont("Arial", 16)); layout.addWidget(radio); button_group.addButton(radio, i)
                self.udf_main_layout.addWidget(group_box); self.udf_widgets.append({"group": group_box, "buttons": button_group, "data": udf_data})
        self._update_all_plates()
    def _setup_ui(self, main_layout):
        self.main_layout = main_layout; main_layout.setContentsMargins(0,0,0,0); scroll_area = QScrollArea(); scroll_area.setWidgetResizable(True); scroll_area.setStyleSheet("QScrollArea { border: none; }"); self.grab_container = QWidget(); scroll_area.setWidget(self.grab_container); content_layout = QVBoxLayout(self.grab_container); top_bar_layout = QHBoxLayout(); info_layout = QHBoxLayout(); self.back_button = QPushButton("← Tilbake til menyen"); self.back_button.setMinimumHeight(80); self.back_button.setFont(QFont("Arial", 20)); top_bar_layout.addWidget(self.back_button); top_bar_layout.addSpacerItem(QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)); self.script_name_label = QLabel("Script Navn"); self.script_name_label.setFont(QFont("Arial", 32, QFont.Bold)); self.script_name_label.setAlignment(Qt.AlignCenter); self.thumbnail_label = QLabel(); self.thumbnail_label.setFixedSize(225, 150); self.thumbnail_label.setScaledContents(True); self.thumbnail_label.setAlignment(Qt.AlignCenter); self.thumbnail_label.setStyleSheet("border: 1px solid #ccc;"); self.description_label = QLabel("Beskrivelse her..."); self.description_label.setFont(QFont("Arial", 16)); self.description_label.setWordWrap(True); info_vbox = QVBoxLayout(); info_vbox.addWidget(self.description_label); info_vbox.addStretch(1); info_layout.addWidget(self.thumbnail_label); info_layout.addLayout(info_vbox); self.sample_range_label = QLabel("Gyldig antall: 1 - 96"); self.sample_range_label.setFont(QFont("Arial", 14, italic=True)); 
        samples_layout = QHBoxLayout(); samples_label = QLabel("Antall prøver:"); samples_label.setFont(QFont("Arial", 24)); self.samples_display = QPushButton("0"); self.samples_display.setFont(QFont("Arial", 24, QFont.Bold)); self.samples_display.setMinimumWidth(120);
        samples_layout.addWidget(samples_label); samples_layout.addWidget(self.samples_display); samples_layout.addStretch(1); 
        self.udf_main_layout = QVBoxLayout(); self.groups_container = QWidget(); self.groups_layout = QHBoxLayout(self.groups_container); self.start_button = QPushButton("START PIPETTERING"); self.start_button.setMinimumHeight(150); self.start_button.setFont(QFont("Arial", 40, QFont.Bold)); self.start_button.setStyleSheet("""QPushButton {background-color: #0078d4; color: white;} QPushButton:disabled {background-color: #5a5a5a; color: #999999;}"""); self.keypad = NumericKeypad(self); self.keypad.setFixedSize(450, 520); self.keypad.hide(); content_layout.addLayout(top_bar_layout); content_layout.addWidget(self.script_name_label); content_layout.addLayout(info_layout); content_layout.addLayout(samples_layout); content_layout.addWidget(self.sample_range_label); content_layout.addLayout(self.udf_main_layout); content_layout.addWidget(self.groups_container); content_layout.addStretch(1); main_layout.addWidget(scroll_area, 1); main_layout.addWidget(self.start_button)
    def _connect_signals(self):
        self.back_button.clicked.connect(self.back_to_menu.emit); self.keypad.enter_pressed.connect(self._confirm_input); self.keypad.key_pressed.connect(self._on_key_pressed); self.samples_display.clicked.connect(lambda: self._set_active_input(self.samples_display)); self.start_button.clicked.connect(self._on_start_pipetting)
    def _confirm_input(self):
        if self.active_input_display == self.samples_display: self._update_all_plates()
        else: self._hide_keypad()
    def _hide_keypad(self):
        self.keypad.hide(); self._set_active_input(None)
    def finalize_new_start_pos(self, well_index):
        if self.active_group_for_editing:
            group = self.active_group_for_editing; group.group_data['currentStartPosition'] = well_index; group.update_displays(); self._update_all_plates(); self.active_group_for_editing = None
    def _on_change_start_pos_clicked(self, group_widget):
        self._hide_keypad(); self.start_button.setEnabled(False); self.active_group_for_editing = group_widget; self.edit_plate_fullscreen.emit(group_widget)
    def _set_active_input(self, display_widget):
        self.samples_display.setStyleSheet("");
        for group in self.box_group_widgets: group.volume_display.setStyleSheet("")
        self.active_input_display = display_widget;
        if self.active_input_display:
            self.active_input_display.setStyleSheet("background-color: #aadeff;"); global_pos = self.active_input_display.mapToGlobal(QPoint(0, self.active_input_display.height())); local_pos = self.mapFromGlobal(global_pos); self.keypad.move(local_pos.x(), local_pos.y() + 5); self.keypad.show(); self.keypad.raise_()
    def _on_volume_display_clicked(self, group_widget):
        self.active_group_for_editing = group_widget; self._set_active_input(group_widget.volume_display)
    def _on_key_pressed(self, key):
        if not self.active_input_display: return
        if self.active_input_display == self.samples_display:
            current_str = self.samples_input
            if key == 'del': current_str = current_str[:-1]
            elif len(current_str) < 3: current_str += key
            self.samples_input = current_str; self.active_input_display.setText(current_str or "0")
        else:
            current_str = self.active_input_display.text()
            if key == 'del': current_str = current_str[:-1]
            elif len(str(current_str)) < 4: current_str += key
            if self.active_group_for_editing:
                self.active_group_for_editing.group_data['volume']['defaultValue'] = int(current_str or "0")
            self.active_input_display.setText(str(current_str or "0"))
    def _update_all_plates(self):
        self._hide_keypad()
        try:
            num_samples = int(self.samples_input or "0"); sample_range = self.script_data.get("sampleRange", {}); min_s, max_s = sample_range.get("min", 1), sample_range.get("max", 96)
            if num_samples != 0 and not (min_s <= num_samples <= max_s):
                QMessageBox.warning(self, "Ugyldig antall", f"Antall prøver må være mellom {min_s} og {max_s}."); return
            for group in self.box_group_widgets:
                start_pos = group.group_data.get('currentStartPosition', 1); disabled = group.group_data.get('disabledWells', []); group.update_plates(num_samples, start_pos, disabled)
            self.start_button.setEnabled(num_samples > 0)
        except (ValueError, AttributeError): print("Kunne ikke oppdatere plater.")
    def _on_start_pipetting(self):
        try:
            visualization_path = self.script_data.get("visualizationFile", "script_visual.png"); size = self.grab_container.size(); pixmap = QPixmap(size); self.grab_container.render(pixmap); pixmap.save(visualization_path); print(f"Bilde av oppsett lagret til: {visualization_path}")
            with open(self.script_data['targetFile'], 'w') as f: f.write(self.script_data['targetValue'])
            with open(self.script_data['sampleCountFile'], 'w') as f: f.write(self.samples_input or "0")
            for group_widget in self.box_group_widgets:
                group_data = group_widget.group_data
                with open(group_data['startPositionFile'], 'w') as f: f.write(str(group_data['currentStartPosition']))
                with open(group_data['volume']['volumeFile'], 'w') as f: f.write(str(group_data['volume']['defaultValue']))
            for udf_widget in self.udf_widgets:
                if udf_widget["buttons"].checkedId() != -1:
                    selected_id = udf_widget["buttons"].checkedId(); selected_option = udf_widget["data"]["options"][selected_id]
                    with open(selected_option['file'], 'w') as f: f.write(str(selected_option['value']))
            print("Konfigurasjon lagret. Lukker GUI."); QApplication.instance().quit()
        except Exception as e:
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
        super().__init__(parent); self.setFrameShape(QFrame.Shape.StyledPanel); layout = QFormLayout(self); font = QFont("Arial", 14); self.group_name_input = QLineEdit(); self.shape_input = QComboBox(); self.shape_input.addItems(["circle", "rect"]); self.max_boxes_input = QLineEdit("1"); self.start_pos_input = QLineEdit("1"); self.disabled_wells_input = QLineEdit(); self.vol_default_input = QLineEdit("500"); self.start_pos_file_input = QLineEdit(); self.volume_file_input = QLineEdit(); remove_button = QPushButton("X Fjern"); remove_button.setStyleSheet("color: red;"); remove_button.clicked.connect(lambda: self.remove_me.emit(self))
        for w in [self.group_name_input, self.shape_input, self.max_boxes_input, self.start_pos_input, self.disabled_wells_input, self.vol_default_input, self.start_pos_file_input, self.volume_file_input, remove_button]: w.setFont(font)
        layout.addRow(remove_button); layout.addRow("Gruppenavn:", self.group_name_input); layout.addRow("Brønnform:", self.shape_input); layout.addRow("Maks antall bokser:", self.max_boxes_input); layout.addRow("Initiell startposisjon:", self.start_pos_input); layout.addRow("Deaktiverte brønner:", self.disabled_wells_input); layout.addRow("Standard volum (µL):", self.vol_default_input); layout.addRow("Fil for startposisjon:", self.start_pos_file_input); layout.addRow("Fil for volum:", self.volume_file_input)
    def get_data(self):
        try: disabled_wells = [int(x.strip()) for x in self.disabled_wells_input.text().split(',') if x.strip()]
        except ValueError: return None
        return {"groupName": self.group_name_input.text() or "Boks Gruppe", "shape": self.shape_input.currentText(), "maxBoxes": int(self.max_boxes_input.text() or "1"), "startPositionFile": self.start_pos_file_input.text(), "initialStartPosition": int(self.start_pos_input.text() or "1"), "disabledWells": disabled_wells, "volume": {"volumeFile": self.volume_file_input.text(), "defaultValue": int(self.vol_default_input.text() or "0"), "min": 0, "max": 5000}}
    def set_data(self, data):
        self.group_name_input.setText(data.get("groupName", "")); self.shape_input.setCurrentText(data.get("shape", "rect")); self.max_boxes_input.setText(str(data.get("maxBoxes", 1))); self.start_pos_input.setText(str(data.get("initialStartPosition", 1))); self.start_pos_file_input.setText(data.get("startPositionFile", "")); disabled_str = ", ".join(map(str, data.get("disabledWells", []))); self.disabled_wells_input.setText(disabled_str); volume = data.get("volume", {}); self.vol_default_input.setText(str(volume.get("defaultValue", 0))); self.volume_file_input.setText(volume.get("volumeFile", ""))

class UDFOptionForm(QWidget):
    remove_me = Signal(object)
    def __init__(self, parent=None):
        super().__init__(parent); font = QFont("Arial", 14); layout = QHBoxLayout(self); self.label_input = QLineEdit(); self.value_input = QLineEdit(); self.file_input = QLineEdit(); remove_button = QPushButton("x"); remove_button.setFixedSize(30,30)
        for w in [self.label_input, self.value_input, self.file_input, remove_button]: w.setFont(font)
        layout.addWidget(QLabel("Tekst:")); layout.addWidget(self.label_input, 1); layout.addWidget(QLabel("Verdi:")); layout.addWidget(self.value_input, 1); layout.addWidget(QLabel("Filsti:")); layout.addWidget(self.file_input, 2); layout.addWidget(remove_button)
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
        super().__init__(parent); self.scripts_dir = scripts_dir; self.editing_folder_name = None; self.box_group_forms = []; self.udf_forms = []
        main_layout = QVBoxLayout(self); scroll_area = QScrollArea(); scroll_area.setWidgetResizable(True); main_layout.addWidget(scroll_area); container = QWidget(); form_layout = QFormLayout(container); form_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows); scroll_area.setWidget(container); font = QFont("Arial", 16)
        self.script_name_input = QLineEdit(); self.target_value_input = QLineEdit(); self.description_input = QTextEdit(); self.thumbnail_input = QLineEdit(); self.sample_min_input = QLineEdit("1"); self.sample_max_input = QLineEdit("96"); self.target_file_input = QLineEdit("C:/robot/selected_script.txt"); self.sample_count_file_input = QLineEdit("C:/robot/variables/sample_count.txt"); self.visualization_file_input = QLineEdit("script_visual.png")
        for w in [self.script_name_input, self.target_value_input, self.description_input, self.thumbnail_input, self.sample_min_input, self.sample_max_input, self.target_file_input, self.sample_count_file_input, self.visualization_file_input]: w.setFont(font)
        form_layout.addRow(QLabel("<h3>Generell Info</h3>")); form_layout.addRow("Navn på script:", self.script_name_input); form_layout.addRow("Verdi for robot:", self.target_value_input); form_layout.addRow("Beskrivelse:", self.description_input); form_layout.addRow("Filnavn for thumbnail:", self.thumbnail_input); sample_range_layout = QHBoxLayout(); sample_range_layout.addWidget(self.sample_min_input); sample_range_layout.addWidget(QLabel("til")); sample_range_layout.addWidget(self.sample_max_input); form_layout.addRow("Antall prøver (min-maks):", sample_range_layout); form_layout.addRow(QLabel("<u>Globale filstier:</u>")); form_layout.addRow("Fil for valgt script:", self.target_file_input); form_layout.addRow("Fil for antall prøver:", self.sample_count_file_input); form_layout.addRow("Fil for visualisering (.png):", self.visualization_file_input)
        form_layout.addRow(QLabel("<h3>Boksgrupper</h3>")); self.box_groups_layout = QVBoxLayout(); form_layout.addRow(self.box_groups_layout); add_group_button = QPushButton("+ Legg til boksgruppe"); add_group_button.setFont(font); add_group_button.clicked.connect(lambda: self._add_box_group_form()); form_layout.addRow(add_group_button)
        form_layout.addRow(QLabel("<h3>Brukerdefinerte valg</h3>")); self.udf_layout = QVBoxLayout(); form_layout.addRow(self.udf_layout); add_udf_button = QPushButton("+ Legg til brukerdefinert valg"); add_udf_button.setFont(font); add_udf_button.clicked.connect(lambda: self._add_udf_form()); form_layout.addRow(add_udf_button)
        back_button = QPushButton("← Avbryt"); back_button.setFont(font); back_button.clicked.connect(self.back_to_settings.emit); save_button = QPushButton("Lagre Script"); save_button.setFont(font); save_button.clicked.connect(self._save_script); button_layout = QHBoxLayout(); button_layout.addWidget(back_button); button_layout.addStretch(1); button_layout.addWidget(save_button); main_layout.addLayout(button_layout)
    def _add_box_group_form(self, data=None):
        form = BoxGroupForm(); form.remove_me.connect(self._remove_box_group_form);
        if data: form.set_data(data)
        self.box_groups_layout.addWidget(form); self.box_group_forms.append(form)
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
    def reset_form(self):
        self._clear_forms()
        self.editing_folder_name = None; self.script_name_input.clear(); self.target_value_input.clear(); self.description_input.clear(); self.thumbnail_input.clear(); self.sample_min_input.setText("1"); self.sample_max_input.setText("96"); self.target_file_input.setText("C:/robot/selected_script.txt"); self.sample_count_file_input.setText("C:/robot/variables/sample_count.txt"); self.visualization_file_input.setText("script_visual.png")
        self._add_box_group_form()
    def load_data_for_edit(self, script_data):
        self._clear_forms()
        self.editing_folder_name = script_data.get('folder_name'); self.script_name_input.setText(script_data.get("scriptName")); self.target_value_input.setText(script_data.get("targetValue", "")); self.description_input.setText(script_data.get("description", "")); self.thumbnail_input.setText(script_data.get("thumbnail", "")); self.target_file_input.setText(script_data.get("targetFile", "")); self.sample_count_file_input.setText(script_data.get("sampleCountFile", "")); self.visualization_file_input.setText(script_data.get("visualizationFile", "script_visual.png")); sample_range = script_data.get("sampleRange", {}); self.sample_min_input.setText(str(sample_range.get("min", 1))); self.sample_max_input.setText(str(sample_range.get("max", 96)))
        for group_data in script_data.get("boxGroups", []): self._add_box_group_form(group_data)
        for udf_data in script_data.get("userDefinedVariables", []): self._add_udf_form(udf_data)
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
        config_data = {"scriptName": script_name, "description": self.description_input.toPlainText(), "thumbnail": self.thumbnail_input.text(), "visualizationFile": self.visualization_file_input.text(), "targetFile": self.target_file_input.text(), "targetValue": self.target_value_input.text(), "sampleCountFile": self.sample_count_file_input.text(), "sampleRange": { "min": int(self.sample_min_input.text() or 1), "max": int(self.sample_max_input.text() or 96) }, "boxGroups": box_groups_data, "userDefinedVariables": udf_data}
        try:
            script_folder_path = self.scripts_dir / folder_name; os.makedirs(script_folder_path, exist_ok=True)
            with open(script_folder_path / "config.json", 'w', encoding='utf-8') as f: json.dump(config_data, f, indent=4)
            QMessageBox.information(self, "Suksess", f"Scriptet '{script_name}' ble lagret!"); self.back_to_settings.emit()
        except Exception as e: QMessageBox.critical(self, "Feil", f"Kunne ikke lagre script:\n{e}")