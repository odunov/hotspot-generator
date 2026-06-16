# Hotspot Base Map Generator

Blender 5.x extension for drawing rectangular hotspot atlases and exporting texture-ready ID, mask, height, normal, AO, and curvature maps.

## Features

- One scene-level hotspot canvas stored as Blender scene property data.
- Image Editor sidebar panels for canvas, cutter, region, overlay, and export controls.
- Recursive horizontal/vertical region splits with arbitrary ratios.
- Equal `2x2` and custom rows/columns grid subdivision.
- Image Editor Paint toolbar cutter tool with midpoint, unsnapped, loop-cut, and square-grid cut modes.
- Live debounced GPU preview in the Image Editor, with CPU fallback.
- Generated ID, Edge, Mask, Height, Normal, AO, and Curvature maps.
- Deterministic color, sequential grayscale, and stored per-region color modes.
- Global rendered gutter/padding, hard edge width, height/bevel, normal, AO, and curvature settings.
- PNG export using map suffixes such as `<stem>_ID.png`, `<stem>_Normal.png`, and `<stem>_Curvature.png`.

## Installation

1. Download the latest `hotspot_base_map_generator-*.zip` from Releases.
2. In Blender, open Preferences, then Extensions.
3. Use Install from Disk and select the zip file.
4. Enable Hotspot Base Map Generator.

## Basic Use

1. Open the Image Editor.
2. Create a hotspot canvas from the Hotspot sidebar.
3. Split regions with the sidebar controls or the cutter tool.
4. Preview the generated maps in Blender.
5. Export the selected PNG maps for use in your texturing workflow.
