# Hotspot Base Map Generator Plan

## Summary

Build a pure Blender Python extension for non-destructive hotspot atlas authoring. The Image Editor is the main workspace, the scene property data is the source of truth, and generated Blender `Image` datablocks plus exported PNGs are derived output.

## Implemented

- Blender 5.x extension scaffold with `blender_manifest.toml`.
- Scene-level `Scene.hotspot_project` data model with flat `HotspotNode` storage.
- Normalized rectangle tree layout, leaf derivation, validation, hit testing, and deterministic bounds.
- Image Editor sidebar panels and region list.
- Overlay outlines, active-region highlight, and cutter preview lines.
- Region split operators, arbitrary split ratios, `2x2`, custom grid subdivision, and loop-cut style cutter tool.
- Cutter hotkeys for midpoint snap, grid mode, and cut/grid amount adjustment.
- Live debounced preview into Blender image datablocks.
- ID, Edge, Mask, Height, Normal, AO, and Curvature map generation.
- Deterministic color, sequential grayscale, stored region colors, global gutter, hard edge width, height/bevel, normal, AO, and curvature controls.
- Export checkboxes and PNG export for `_ID`, `_Edge`, `_Mask`, `_Height`, `_Normal`, `_AO`, and `_Curvature` maps.
- Pure Python tests and Blender background smoke test.

## Next Core Work

- Manually test the generated Height, Normal, AO, and Curvature maps in Substance Painter or a similar texturing workflow.
- Tune defaults if the maps read too harsh, too soft, or too low contrast.
- Add per-region overrides only after global controls feel correct.

## Height Pipeline

- Generate a grayscale height field from rendered leaf geometry.
- Use current layout bounds, gutter, and map resolution as the base.
- Add global controls:
  - `height_depth`
  - `base_height`
  - `bevel_width`
  - `bevel_strength`
  - `corner_radius`
  - `edge_softness`
- Shape bevels from distance-to-border so interiors stay stable and edges transition smoothly.
- Support rounded corners with signed-distance style rectangle math.
- Output `_Height.png` as non-color grayscale data. Implemented globally; per-region overrides are still future work.

## Derived Maps

- Normal: generated from Height using neighboring pixel gradients, with strength and OpenGL/DirectX format controls.
- AO: approximate cavity/ambient occlusion from local height differences.
- Curvature: approximate from the second derivative / Laplacian of Height.

## Integration Work

- Preview selector, generated image cache names, export checkboxes, and suffix naming now cover all seven maps.
- Pure raster tests cover height ramps, normal direction, DirectX green flip, AO response, and curvature response.
- Blender smoke test confirms generated image datablocks and filenames exist.

## Deferred Polish

- Cutter status bar wording.
- Panel grouping cleanup.
- Export/report wording.
- Performance checks unless generation becomes visibly slow.
- README screenshots and usage polish.
- Overlay labels.
- Click-to-select existing leaves.
- Layout presets.
- Draggable split lines and direct manipulation.
- Merge/delete leaf regions if the binary tree model can support it cleanly.
- Metadata JSON export.

## Assumptions

- One active canvas per scene remains enough for now.
- Runtime dependencies stay Blender Python and Python stdlib only.
- Generated images are cache/output only and can always be regenerated.
- Substance Painter integration means exported files, not Substance automation.
- Reliable development refresh is repo edit, sync to Blender, relaunch Blender.
- Height is the source for Normal, AO, and Curvature.
- Normal-to-height is not part of this tool.
