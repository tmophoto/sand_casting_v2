#!/usr/bin/env python3
# Part 3: Complete MainWindow class - part B (event handlers)

with open('C:/Users/tmoph/OneDrive/Documents/Claude_code/sand_casting_v2/casting_sim.py', 'r') as f:
    content = f.read()

if '_on_gating_moved' in content:
    print("Part 3 part B already appended")
else:
    part3_partB = '''

    def _on_gating_moved(self, data):
        """Sync sliders from 3D drag operations."""
        self.sprue_x_slider.blockSignals(True)
        self.sprue_y_slider.blockSignals(True)
        self.riser_x_slider.blockSignals(True)
        self.riser_y_slider.blockSignals(True)

        self.sprue_x_slider.setValue(int(data.get("sprue_x", 0)))
        self.sprue_y_slider.setValue(int(data.get("sprue_y", 0)))
        self.riser_x_slider.setValue(int(data.get("riser_x", 0)))
        self.riser_y_slider.setValue(int(data.get("riser_y", 0)))

        self.sprue_x_slider.blockSignals(False)
        self.sprue_y_slider.blockSignals(False)
        self.riser_x_slider.blockSignals(False)
        self.riser_y_slider.blockSignals(False)

    def _on_load_stl(self):
        """Handle STL file load button click."""
        filename, _ = QFileDialog.getOpenFileName(
            self, "Load STL File", "", "STL Files (*.stl);;All Files (*)"
        )
        if filename:
            try:
                stats = self.viewport.load_stl(filename)
                self.stl_label.setText("Loaded: " + filename + chr(10) + "Volume: " + str(round(stats['vol_cm3'], 2)) + " cm^3" + chr(10) + "Surface: " + str(round(stats['surf_cm2'], 2)) + " cm^2")
                self._geometry_stats = stats
            except Exception as e:
                QMessageBox.critical(self, "Error", "Failed to load STL:" + chr(10) + str(e))

    def _on_parting_changed(self, val):
        """Handle parting line slider change."""
        frac = val / 100.0
        self.viewport.set_parting(frac)
        parent_widget = self.parting_slider.parent()
        if parent_widget:
            for i in range(parent_widget.layout().count()):
                widget = parent_widget.layout().itemAt(i).widget()
                if isinstance(widget, QLabel) and "Position:" in widget.text():
                    widget.setText("Position: " + str(val) + "%")
                    break

    def _on_metal_changed(self, index):
        """Handle metal combo box change."""
        metal_name = self.metal_combo.currentText()
        pour_temp = METAL_DEFAULTS[metal_name]["pour_temp_f"]
        shrink_pct = METAL_DEFAULTS[metal_name]["shrinkage_pct"]

        self.pour_spin.setValue(pour_temp)
        self.shrink_label.setText("Shrinkage: " + str(shrink_pct) + "% (" + metal_name + ")")

    def _on_flask_changed(self, text):
        """Handle flask size combo box change."""
        size = self._flask_presets.get(text, (8, 10))
        self.viewport.set_flask(size)

    def _on_add_flask_preset(self):
        """Add custom flask preset."""
        text, ok = QInputDialog.getText(
            self, "Add Custom Flask",
            "Enter name, width, height (e.g., '10x12, 10, 12'):"
        )
        if ok and text:
            try:
                parts = text.replace(" ", "").split(",")
                name = parts[0]
                width = float(parts[1])
                height = float(parts[2])
                self._flask_presets[name] = (width, height)
                self.flask_combo.addItem(name)
            except Exception as e:
                QMessageBox.warning(self, "Error", "Invalid format: " + str(e))
'''

    with open('C:/Users/tmoph/OneDrive/Documents/Claude_code/sand_casting_v2/casting_sim.py', 'a') as f:
        f.write(part3_partB)

    print("Part 3 (part B) written - event handlers")
