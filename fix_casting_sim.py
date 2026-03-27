#!/usr/bin/env python3
"""Fix casting_sim.py by removing duplicate _build_ui and adding missing handlers."""

# Read the file
with open('C:/Users/tmoph/OneDrive/Documents/Claude_code/sand_casting_v2/casting_sim.py', 'r') as f:
    lines = f.readlines()

print(f"Total lines in file: {len(lines)}")

# Find line positions (0-indexed)
_build_ui1_start = None
_build_ui2_start = None
_wire_signals_end = None

for i, line in enumerate(lines):
    if line.strip().startswith('def _build_ui(self):'):
        if _build_ui1_start is None:
            _build_ui1_start = i
        else:
            _build_ui2_start = i
    if 'self._on_flask_changed(self.flask_combo.currentText())' in line:
        _wire_signals_end = i

print(f"First _build_ui starts at line {_build_ui1_start + 1}")
print(f"Second _build_ui starts at line {_build_ui2_start + 1}")
print(f"_wire_signals ends at line {_wire_signals_end + 1}")

# Remove everything from first _build_ui to just before second _build_ui
new_lines = lines[:_build_ui1_start] + lines[_build_ui2_start:]

print(f"After removing duplicate: {len(new_lines)} lines")

# Find where to insert handler methods (after _wire_signals, before build_results_text)
insert_pos = None
for i, line in enumerate(new_lines):
    if 'def build_results_text(r):' in line:
        insert_pos = i
        break

print(f"Will insert handlers at line {insert_pos + 1}")

# Handler methods to add
handler_methods = '''
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

    def _on_simulate(self):
        """Run the casting simulation."""
        # Gather all parameters
        metal_name = self.metal_combo.currentText()
        metal_params = METAL_DEFAULTS[metal_name]

        params = {
            'metal': metal_name,
            'pour_f': self.pour_spin.value(),
            'mold_f': self.mold_spin.value(),
            'thin_wall': self.thin_combo.currentIndex() == 1,
            'shrinkage': metal_params['shrinkage_pct'],
            'gate_types': [name for name, cb in self.gating_checkboxes.items() if cb.isChecked()],
        }

        # Run simulation in a thread
        self.progress_bar.setVisible(True)
        self.sim_btn.setEnabled(False)
        self.reset_btn.setEnabled(False)

        self._sim_thread = QThread()
        self._sim_worker = SimWorker(params)
        self._sim_worker.moveToThread(self._sim_thread)

        self._sim_worker.progress.connect(lambda pct, msg: self._on_sim_progress(pct, msg))
        self._sim_worker.finished.connect(lambda result: self._on_sim_done(result))
        self._sim_thread.started.connect(self._sim_worker.run)

        self._sim_thread.start()

    def _on_sim_progress(self, pct, msg):
        """Update progress during simulation."""
        self.progress_bar.setValue(int(pct * 100))
        self.progress_bar.setFormat(msg + " %p%")

    def _on_sim_done(self, result):
        """Handle simulation completion."""
        self.progress_bar.setVisible(False)
        self.sim_btn.setEnabled(True)
        self.reset_btn.setEnabled(True)

        if result:
            self._last_result = result
            self.results_text.setText(build_results_text(result))
        else:
            self.results_text.setText("Simulation failed or was cancelled.")

    def _on_reset(self):
        """Reset the application state."""
        # Reset sliders to defaults
        self.pour_spin.setValue(660)
        self.mold_spin.setValue(100)
        self.x_slider.setValue(0)
        self.y_slider.setValue(0)
        self.z_slider.setValue(0)
        self.rot_slider.setValue(0)
        self.sprue_x_slider.setValue(0)
        self.sprue_y_slider.setValue(0)
        self.riser_x_slider.setValue(0)
        self.riser_y_slider.setValue(0)

        # Reset checkboxes
        for cb in self.gating_checkboxes.values():
            cb.setChecked(False)

        # Clear results
        self.results_text.setText("")
        self.stl_label.setText("No file loaded")
        self._last_result = None

'''

# Insert handler methods
new_lines.insert(insert_pos, handler_methods)

print(f"After adding handlers: {len(new_lines)} lines")

# Write the fixed file
with open('C:/Users/tmoph/OneDrive/Documents/Claude_code/sand_casting_v2/casting_sim.py', 'w') as f:
    f.writelines(new_lines)

print("File fixed successfully!")
