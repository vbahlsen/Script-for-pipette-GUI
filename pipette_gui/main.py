# Filnavn: main.py

import sys
import pathlib
from PySide6.QtWidgets import QApplication, QMainWindow, QStackedWidget, QPushButton, QWidget, QVBoxLayout
from PySide6.QtCore import Qt, QTimer, Signal

from gui_screens import ScriptSelectorScreen, ScriptDetailScreen, SettingsScreen, GeneratorScreen
from gui_widgets import WellPlateWidget

BASE_DIR = pathlib.Path(__file__).resolve().parent

class FullScreenEditor(QWidget):
    well_selected = Signal(int)
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.plate_widget = WellPlateWidget(fixed_size=False)
        self.plate_widget.well_clicked.connect(self.well_selected.emit)
        layout.addWidget(self.plate_widget)
    def set_plate(self, shape, start_pos, sample_count, disabled_wells, frame_color=None):
        if self.plate_widget.shape != shape:
            new_plate = WellPlateWidget(shape=shape, fixed_size=False)
            self.layout().replaceWidget(self.plate_widget, new_plate)
            self.plate_widget.deleteLater()
            self.plate_widget = new_plate
            self.plate_widget.well_clicked.connect(self.well_selected.emit)
        self.plate_widget.set_state(start_pos, sample_count, disabled_wells, frame_color)
        self.plate_widget.set_interactive(True)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pipetteringsrobot GUI")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.scripts_dir = BASE_DIR / "scripts"
        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)
        self.selector_screen = ScriptSelectorScreen(base_dir=BASE_DIR)
        self.detail_screen = ScriptDetailScreen(base_dir=BASE_DIR)
        self.fullscreen_editor = FullScreenEditor()
        self.settings_screen = SettingsScreen(base_dir=BASE_DIR)
        self.generator_screen = GeneratorScreen(scripts_dir=self.scripts_dir)
        self.stacked_widget.addWidget(self.selector_screen)
        self.stacked_widget.addWidget(self.detail_screen)
        self.stacked_widget.addWidget(self.fullscreen_editor)
        self.stacked_widget.addWidget(self.settings_screen)
        self.stacked_widget.addWidget(self.generator_screen)
        self.selector_screen.script_selected.connect(self.show_detail_screen)
        self.selector_screen.settings_clicked.connect(self.show_settings_screen)
        self.settings_screen.back_to_menu.connect(self.show_selector_screen)
        self.settings_screen.open_generator.connect(self.show_generator_screen)
        self.settings_screen.open_generator_for_edit.connect(self.show_generator_for_edit)
        self.generator_screen.back_to_settings.connect(self.show_settings_screen)
        self.detail_screen.back_to_menu.connect(self.show_selector_screen)
        self.detail_screen.edit_plate_fullscreen.connect(self.show_fullscreen_editor)
        self.fullscreen_editor.well_selected.connect(self.handle_fullscreen_selection)
        close_button = QPushButton("X", self)
        screen_width = self.screen().geometry().width()
        close_button.setGeometry(screen_width - 60, 10, 50, 50)
        close_button.setStyleSheet("background-color: #c00000; color: white; font-size: 24px; border-radius: 25px; font-weight: bold;")
        close_button.clicked.connect(self.close_application)
        self.show_selector_screen()
    def show_selector_screen(self):
        self.selector_screen.load_scripts()
        self.stacked_widget.setCurrentWidget(self.selector_screen)
    def show_settings_screen(self):
        self.settings_screen.populate_scripts_list()
        self.stacked_widget.setCurrentWidget(self.settings_screen)
    def show_generator_screen(self):
        self.generator_screen.reset_form()
        self.stacked_widget.setCurrentWidget(self.generator_screen)
    def show_generator_for_edit(self, script_data):
        self.generator_screen.load_data_for_edit(script_data)
        self.stacked_widget.setCurrentWidget(self.generator_screen)
    def show_detail_screen(self, script_data):
        # Only switch to the detail screen if loading was successful
        if self.detail_screen.load_script_data(script_data):
            self.stacked_widget.setCurrentWidget(self.detail_screen)
        else:
            # If loading failed, go back to the script selector screen
            self.stacked_widget.setCurrentWidget(self.selector_screen)
    def show_fullscreen_editor(self, group_widget):
        try:
            self.detail_screen.active_group_for_editing = group_widget
            plate_data = group_widget.group_data
            shape = plate_data.get("shape", "rect")
            start_pos = plate_data.get("currentStartPosition", 1)
            disabled_wells = plate_data.get("disabledWells", [])
            
            # Handle missing color field gracefully
            frame_color = plate_data.get("color")  # Will be None if missing
            
            self.fullscreen_editor.plate_widget.temp_selected_well = None
            
            try:
                # Try with color first
                if frame_color:
                    self.fullscreen_editor.set_plate(shape, start_pos, 0, disabled_wells, frame_color)
                else:
                    # Fall back to default gray if no color specified
                    self.fullscreen_editor.set_plate(shape, start_pos, 0, disabled_wells, "#808080")
            except Exception as e:
                print(f"Error setting plate with color: {e}")
                # Ultimate fallback without color parameter
                self.fullscreen_editor.set_plate(shape, start_pos, 0, disabled_wells)
                
            self.stacked_widget.setCurrentWidget(self.fullscreen_editor)
        except Exception as e:
            print(f"Error showing fullscreen editor: {e}")
    def handle_fullscreen_selection(self, well_index):
        self.fullscreen_editor.plate_widget.temp_selected_well = well_index
        self.fullscreen_editor.plate_widget.update()
        QTimer.singleShot(1000, lambda: self.return_from_editor(well_index))

    def return_from_editor(self, well_index):
        # FIKS: Kall den nye funksjonen som setter posisjonen direkte
        self.detail_screen.finalize_new_start_pos(well_index)
        self.stacked_widget.setCurrentWidget(self.detail_screen)

    def close_application(self):
        print("Lukker applikasjonen...")
        QApplication.instance().quit()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.showFullScreen()
    sys.exit(app.exec())