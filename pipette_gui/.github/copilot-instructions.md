# Pipette GUI Project - AI Assistant Guide

## Project Overview
This is a touchscreen GUI application for controlling pipetting robots in a laboratory setting. The app manages pipetting scripts, visualizes 96-well plates, and handles user input through a custom numeric keypad interface.

## Core Architecture

### Component Structure
- `main.py` - Application entry point and window management
- `gui_screens.py` - Main screen implementations (Selector, Detail, Settings, Generator)
- `gui_widgets.py` - Reusable UI components (WellPlate, Keypad, etc.)
- `custom_widgets.py` - Enhanced input widgets with consistent behavior

### Key Design Patterns
1. Screen-based Navigation
   ```python
   # Screens are managed through QStackedWidget in MainWindow
   self.stacked_widget.setCurrentWidget(self.detail_screen)
   ```

2. Configuration-driven Script Management
   - Each script has its own folder with `config.json`
   - Config defines layout, box groups, and file paths

3. Two-phase Input Handling
   ```python
   # Input changes are stored temporarily until confirmed
   self.temp_sample_input = current_str  # Store temp value
   self._update_all_plates()  # Update UI only after confirmation
   ```

## Critical Workflows

### Input Field Behavior
- ALL input fields using numeric keypad must:
  - Auto-select text on focus
  - Show changes immediately but defer updates until Enter
  - Maintain consistent styling when active/inactive

### Well Plate Visualization
- Color coding indicates well status:
  - Yellow: Before start position
  - Dark Green: Start position
  - Light Green: Active samples
  - Grey: Disabled wells
  - White: Available wells

## Integration Points

### File I/O
- Scripts write to `.txt` files in robot's variables directory
- File paths are defined in script's `config.json`
- Standard file structure:
  ```
  robot/
    variables/
      sample_count.txt
      [script_name]/
        specific_variables.txt
  ```

### Language & UI Conventions
- UI text in Norwegian
- Consistent font usage:
  - Headers: Arial 24-48pt Bold
  - Input fields: Arial 24pt Bold
  - Regular text: Arial 16pt

## Development Guidelines

1. Script Compatibility
   - All scripts must provide:
     - Unique folder name
     - Valid `config.json`
     - Thumbnail image
     - Required file paths

2. UI Component Updates
   - Always handle both immediate feedback and deferred updates
   - Clear component state when hiding/showing
   - Validate input ranges before applying changes

3. Error Handling
   - Display errors in Norwegian
   - Use QMessageBox for user-facing errors
   - Handle file I/O errors gracefully