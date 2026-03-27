#!/usr/bin/env python3
"""Fix PyQt6 Qt.Horizontal/Vertical to Qt.Orientation.Horizontal/Vertical."""

import re

# Read the file
with open('C:/Users/tmoph/OneDrive/Documents/Claude_code/sand_casting_v2/casting_sim.py', 'r') as f:
    content = f.read()

# Replace Qt.Horizontal with Qt.Orientation.Horizontal
content = content.replace('Qt.Horizontal', 'Qt.Orientation.Horizontal')

# Replace Qt.Vertical with Qt.Orientation.Vertical
content = content.replace('Qt.Vertical', 'Qt.Orientation.Vertical')

# Write back
with open('C:/Users/tmoph/OneDrive/Documents/Claude_code/sand_casting_v2/casting_sim.py', 'w') as f:
    f.write(content)

print("Orientation fix applied successfully!")
