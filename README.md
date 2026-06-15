# Hotspot Base Map Generator

Blender 5.x extension MVP for non-destructive rectangular hotspot atlas authoring.

The first pass supports:

- one scene-level hotspot canvas
- recursive 50/50 horizontal and vertical splits
- deterministic ID/base-color map generation into a Blender Image datablock
- PNG export for Substance Painter or other texturing tools
- pure Python layout/raster tests that run outside Blender

The repository root is the extension root: it contains both `blender_manifest.toml`
and the shim `__init__.py` that Blender expects. Install or build the repository
folder as a Blender extension during development.

Optional Blender smoke test:

```powershell
blender --background --python tests/blender_smoke.py
```
