# Changelog

## 0.1.1 - 2026-06-17

- Default rendering now fails clearly when GPU rendering is unavailable instead of silently falling back to slow CPU rendering.
- Added an opt-in `Allow Slow CPU Fallback` setting for users who still need the CPU path.
- Made add-on registration roll back partially registered modules/classes on failure.
