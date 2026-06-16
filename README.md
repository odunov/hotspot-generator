# Hotspot Base Map Generator

Blender 5.x extension for non-destructive rectangular hotspot atlas authoring in the Image Editor.

## Current Features

- One scene-level hotspot canvas stored as Blender scene property data.
- Image Editor sidebar panels for canvas, cutter, region, overlay, and export controls.
- Recursive horizontal/vertical region splits with arbitrary ratios.
- Equal `2x2` and custom rows/columns grid subdivision.
- Image Editor Paint toolbar cutter tool with midpoint, unsnapped, loop-cut, and square-grid cut modes.
- Live debounced GPU preview in the Image Editor, with CPU fallback.
- Generated ID, Edge, Mask, Height, Normal, AO, and Curvature maps.
- Deterministic color, sequential grayscale, and stored per-region color modes.
- Global rendered gutter/padding, hard edge width, height/bevel, normal, AO, and curvature settings.
- PNG export using map suffixes such as `<stem>_ID.png`, `<stem>_Normal.png`, and `<stem>_Curvature.png`; height-derived Blender images use float buffers before PNG save.
- Pure Python model/raster tests and a Blender background smoke test.

## Development

Source of truth is this repository:

```text
C:\Users\User\Documents\Hotspot
```

Runtime files are synced into Blender with:

```powershell
powershell -ExecutionPolicy Bypass -File tools\sync_to_blender.ps1
```

Reliable refresh loop:

1. Edit files in this repo.
2. Sync to Blender.
3. Relaunch Blender.

Do not edit the installed Blender extension copy directly.

## Tests

Pure Python tests:

```powershell
python -m unittest discover -s tests -p 'test_*.py'
```

Compile check:

```powershell
python -m compileall __init__.py hotspot_base_map_generator tests
```

Blender smoke test:

```powershell
& 'C:\ART\Blender\blender.exe' --factory-startup --background --python tests\blender_smoke.py
```

## Roadmap

See [PLAN.md](PLAN.md).
