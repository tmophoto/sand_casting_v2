#!/usr/bin/env python3
# Part 3: Complete MainWindow class - part A (_wire_signals method)

with open('C:/Users/tmoph/OneDrive/Documents/Claude_code/sand_casting_v2/casting_sim.py', 'r') as f:
    content = f.read()

if 'def _wire_signals' in content:
    print("Part 3 already appended")
else:
    part3_partA = '''
        # Store reference to main layout for potential updates
        self._main_layout = main_layout

    def _wire_signals(self):
        """Connect all UI signals to their handlers."""
        # STL Load button
        self.load_btn.clicked.connect(self._on_load_stl)

        # Parting slider
        self.parting_slider.valueChanged.connect(self._on_parting_changed)

        # Gating checkboxes
        for name, cb in self.gating_checkboxes.items():
            cb.stateChanged.connect(lambda state, n=name: self.viewport.update_gating_display(n))

        # Metal combo box
        self.metal_combo.currentIndexChanged.connect(self._on_metal_changed)

        # Flask combo box
        self.flask_combo.currentTextChanged.connect(self._on_flask_changed)

        # Add custom flask button
        self.add_flask_btn.clicked.connect(self._on_add_flask_preset)

        # Simulation button
        self.sim_btn.clicked.connect(self._on_simulate)

        # Reset button
        self.reset_btn.clicked.connect(self._on_reset)

        # Model placement sliders - X, Y, Z, Rotation
        def update_transform():
            dx = self.x_slider.value()
            dy = self.y_slider.value()
            dz = self.z_slider.value()
            rot = self.rot_slider.value()
            self.viewport.set_transformation(dx, dy, dz, rot)

        self.x_slider.valueChanged.connect(lambda v: (self.x_slider.setValue(v), update_transform()))
        self.y_slider.valueChanged.connect(lambda v: (self.y_slider.setValue(v), update_transform()))
        self.z_slider.valueChanged.connect(lambda v: (self.z_slider.setValue(v), update_transform()))
        self.rot_slider.valueChanged.connect(lambda v: (self.rot_slider.setValue(v), update_transform()))

        # Gating placement sliders - Sprue X, Y
        def update_gating():
            sprue_x = self.sprue_x_slider.value()
            sprue_y = self.sprue_y_slider.value()
            riser_x = self.riser_x_slider.value()
            riser_y = self.riser_y_slider.value()
            runner_y = 0
            self.viewport.set_gating_offset(sprue_x, sprue_y, runner_y, riser_x, riser_y)

        self.sprue_x_slider.valueChanged.connect(lambda v: (self.sprue_x_slider.setValue(v), update_gating()))
        self.sprue_y_slider.valueChanged.connect(lambda v: (self.sprue_y_slider.setValue(v), update_gating()))
        self.riser_x_slider.valueChanged.connect(lambda v: (self.riser_x_slider.setValue(v), update_gating()))
        self.riser_y_slider.valueChanged.connect(lambda v: (self.riser_y_slider.setValue(v), update_gating()))

        # Pour rate slider
        def on_pour_rate_changed(val):
            rate = 0.1 + (val / 50.0)
            self.viewport.set_pour_rate(rate)

        self.pour_spin.valueChanged.connect(on_pour_rate_changed)

        # Shrinkage slider
        def update_shrink_label(val):
            pct = METAL_DEFAULTS[self.metal_combo.currentText()]["shrinkage_pct"]
            scale = 1.0 + (val - 100) / 1000.0
            self.shrink_label.setText("Shrinkage: " + str(pct) + "% (" + self.metal_combo.currentText() + ")")

        self.shrink_slider.valueChanged.connect(update_shrink_label)

        # Viewport gating moved signal
        self.viewport.gating_moved.connect(self._on_gating_moved)

        # Initial flask setup
        self._on_flask_changed(self.flask_combo.currentText())
'''

    with open('C:/Users/tmoph/OneDrive/Documents/Claude_code/sand_casting_v2/casting_sim.py', 'a') as f:
        f.write(part3_partA)

    print("Part 3 (part A) written - _wire_signals method")
