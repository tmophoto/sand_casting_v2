#!/usr/bin/env python3
"""Remove duplicate build_results_text function from casting_sim.py."""

# Read the file
with open('C:/Users/tmoph/OneDrive/Documents/Claude_code/sand_casting_v2/casting_sim.py', 'r') as f:
    lines = f.readlines()

print(f"Total lines in file: {len(lines)}")

# Find the duplicate build_results_text and remove it
build_results_start = None
build_results_end = None

for i, line in enumerate(lines):
    if 'def build_results_text(r):' in line and i > 2500:  # Second occurrence
        build_results_start = i
    if build_results_start is not None and i > build_results_start and line.strip().startswith('return chr'):
        build_results_end = i + 1
        break

print(f"Duplicate build_results_text starts at line {build_results_start + 1}")
print(f"Ends at line {build_results_end}")

# Remove the duplicate
new_lines = lines[:build_results_start] + lines[build_results_end:]

print(f"After removing duplicate: {len(new_lines)} lines")

# Write back
with open('C:/Users/tmoph/OneDrive/Documents/Claude_code/sand_casting_v2/casting_sim.py', 'w') as f:
    f.writelines(new_lines)

print("Duplicate removed successfully!")
