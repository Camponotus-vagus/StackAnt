## 2025-05-14 - [Accessible Controls Pattern]
**Learning:** PyQt6 widgets like QPushButton often lack explicit accessible names, especially when using icon-only or abbreviated labels. Combining `setToolTip` with `setAccessibleName` ensures both visual guidance and screen reader support.
**Action:** Always provide both `setToolTip` and `setAccessibleName` for interactive controls to maintain high accessibility standards.

## 2025-05-14 - [Interactive Feedback for Clipboard Actions]
**Learning:** Users appreciate immediate confirmation for silent actions like "Copy to Clipboard". A temporary label change (e.g., "Copied!") using a `QTimer` is an effective, lightweight way to provide this feedback without intrusive popups.
**Action:** Implement "Copied!" feedback for all clipboard-copying interactions using a 2-second timer.
