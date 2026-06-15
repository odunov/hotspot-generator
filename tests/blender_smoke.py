"""Optional Blender smoke test.

Run with:
    blender --factory-startup --background --python tests/blender_smoke.py
"""

import os
import sys
import tempfile

import bpy


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import hotspot_base_map_generator as hbmg  # noqa: E402
from hotspot_base_map_generator import operators, properties, tools  # noqa: E402
from hotspot_base_map_generator.model.layout import derive_leaf_regions  # noqa: E402


def image_paint_tool_ids():
    from bl_ui.space_toolsystem_toolbar import IMAGE_PT_tools_active

    ids = []
    for item in IMAGE_PT_tools_active._tools["PAINT"]:
        if item is None:
            continue
        if type(item) is tuple:
            ids.extend(getattr(child, "idname", "") for child in item)
        else:
            ids.append(getattr(item, "idname", ""))
    return ids


def rounded_bounds(leaf):
    bounds = leaf.bounds
    return tuple(round(value, 6) for value in (bounds.x0, bounds.y0, bounds.x1, bounds.y1))


def main():
    hbmg.register()
    scene = bpy.context.scene
    project = scene.hotspot_project
    project.settings.resolution = 64
    project.settings.export_directory = tempfile.mkdtemp(prefix="hbmg_")
    project.settings.export_stem = "smoke"
    assert tools.HOTSPOT_WST_region_cutter.bl_idname == "hotspot.region_cutter", "Unexpected cutter tool id"
    assert "hotspot.region_cutter" in image_paint_tool_ids(), "Cutter tool was not registered in the Image Editor Paint toolbar"
    assert project.settings.cut_preview_width == 2.0, "Unexpected default cutter line width"
    assert not hasattr(hbmg.operators, "HOTSPOT_OT_reload_scripts"), "Reload Scripts operator should not be exposed"
    assert not hasattr(hbmg.ui, "HOTSPOT_PT_development"), "Development reload panel should not be exposed"
    keymap = tools._keymap_from_context(bpy.context)
    assert keymap is not None, "Cutter keymap was not created"
    assert tools._find_keymap_item(keymap, "hotspot.cut_region_at_cursor") is not None, "Cutter cut keymap item missing"
    assert tools._find_keymap_item(keymap, "hotspot.adjust_grid_size", 1) is not None, "Cutter grid-size keymap item missing"
    class FakeArea:
        type = "VIEW_3D"

    class FakeContext:
        area = FakeArea()
        space_data = None
        workspace = bpy.context.workspace

    tools.set_status_text(FakeContext())
    assert not tools._status_text_active, "Cutter status text should ignore non-Image Editor contexts"
    tools.clear_status_text(bpy.context)
    assert not tools._status_text_active, "Cutter status text was not cleared"

    bpy.ops.hotspot.new_canvas()
    project.is_dirty = False
    bpy.ops.hotspot.toggle_midpoint_snap()
    assert not project.settings.cutter_midpoint_snap, "Midpoint snap toggle did not turn snapping off"
    operators.cut_project_at_uv(project, 0.25, 0.9)
    leaves = derive_leaf_regions(properties.nodes_to_records(project))
    assert len(leaves) == 2, f"Expected 2 leaves after unsnapped cutter split, got {len(leaves)}"
    assert project.is_dirty, "Unsnapped cutter split should mark maps dirty"
    assert rounded_bounds(leaves[0]) == (0.0, 0.0, 0.25, 1.0), f"Unexpected unsnapped split bounds: {rounded_bounds(leaves[0])}"

    bpy.ops.hotspot.new_canvas()
    project.is_dirty = False
    project.settings.cutter_grid_enabled = False
    project.settings.cutter_line_cuts = 1
    bpy.ops.hotspot.adjust_grid_size(delta=1)
    assert not project.settings.cutter_grid_enabled, "Line cutter amount adjustment should not enable grid mode"
    assert project.settings.cutter_line_cuts == 2, f"Expected 2 loop cuts, got {project.settings.cutter_line_cuts}"
    _leaf, _action, segment_ids = operators.cut_project_at_uv(project, 0.8, 0.9)
    leaves = derive_leaf_regions(properties.nodes_to_records(project))
    assert len(leaves) == 3, f"Expected 3 leaves after 2 loop cuts, got {len(leaves)}"
    assert project.active_node_id == segment_ids[2], f"Expected clicked segment to be active, got {project.active_node_id}"
    assert rounded_bounds(leaves[0]) == (0.0, 0.0, 0.333333, 1.0), f"Unexpected first loop-cut bounds: {rounded_bounds(leaves[0])}"
    assert rounded_bounds(leaves[2]) == (0.666667, 0.0, 1.0, 1.0), f"Unexpected last loop-cut bounds: {rounded_bounds(leaves[2])}"

    bpy.ops.hotspot.new_canvas()
    project.is_dirty = False
    project.settings.cutter_grid_enabled = False
    project.settings.cutter_grid_size = 2
    bpy.ops.hotspot.toggle_grid_cut()
    assert project.settings.cutter_grid_enabled, "Grid cut toggle did not enable grid mode"
    bpy.ops.hotspot.adjust_grid_size(delta=1)
    assert project.settings.cutter_grid_size == 3, f"Expected 3x3 cutter grid, got {project.settings.cutter_grid_size}"
    operators.cut_project_at_uv(project, 0.5, 0.5)
    leaves = derive_leaf_regions(properties.nodes_to_records(project))
    assert len(leaves) == 9, f"Expected 9 leaves after 3x3 cutter grid subdivision, got {len(leaves)}"
    assert project.is_dirty, "Cutter grid subdivision should mark maps dirty"
    assert project.active_node_id == 6, f"Expected bottom-left cell 6 to be active, got {project.active_node_id}"
    assert rounded_bounds(leaves[0]) == (0.0, 0.0, 0.333333, 0.333333), f"Unexpected bottom-left grid bounds: {rounded_bounds(leaves[0])}"

    project.active_node_id = 999
    project.active_node_index = -1
    active = properties.normalize_active_node(project)
    assert active is not None and properties.is_node_leaf(project, active.node_id), "Invalid active region did not recover to a leaf"

    bpy.ops.hotspot.render_map()
    assert not project.cut_preview_active, "Render should clear stale cutter previews"
    bpy.ops.hotspot.export_maps()

    image = bpy.data.images.get(project.id_image_name)
    assert image is not None, "ID image was not generated"
    assert tuple(image.size) == (64, 64), f"Unexpected image size: {tuple(image.size)}"
    print(f"Hotspot smoke test passed: {project.settings.export_directory}")


if __name__ == "__main__":
    main()
