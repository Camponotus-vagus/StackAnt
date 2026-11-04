# Palette journal

## 2026-11-04 - A QLabel beside an input in a QHBoxLayout is not its label
**Learning:** Screen readers don't associate a separate `QLabel("Pyramid depth:")` with the spin box placed next to it in the layout, so the control is announced only as "spin box". The Advanced options panel had five such inputs, while the main panels already set `setAccessibleName`.
**Action:** For every label + input pair, keep the label in a variable, call `label.setBuddy(input)` and `input.setAccessibleName(...)`. In headless tests, keep a reference to the `QApplication` from `make_app()`, or Qt aborts with "Must construct a QApplication before a QWidget".
