"""Defensive Image Editor overlay for hotspot region outlines."""

import bpy
from bpy.app.handlers import persistent

from . import properties
from .constants import SPLIT_VERTICAL
from .model.layout import (
    choose_cut_orientation,
    cursor_split_ratio,
    derive_leaf_regions,
    find_leaf_at_uv,
    grid_preview_ratios,
    loop_cut_preview_ratios,
)

_handler = None
_shader_cache = None
CUT_TOOL_ID = "hotspot.region_cutter"
CUT_PREVIEW_COLOR = (0.1, 0.42, 1.0, 0.95)
CUT_PREVIEW_WIDTH = 2.0


def _get_shader():
    global _shader_cache
    if _shader_cache is not None:
        return _shader_cache

    import gpu

    for shader_name in ("UNIFORM_COLOR", "2D_UNIFORM_COLOR"):
        try:
            _shader_cache = gpu.shader.from_builtin(shader_name)
            return _shader_cache
        except Exception:
            continue
    return None


def _view_to_region(region, x, y):
    return region.view2d.view_to_region(x, y, clip=False)


def _draw_rect(shader, coords, color, line_width=1.0):
    from gpu_extras.batch import batch_for_shader

    import gpu

    batch = batch_for_shader(shader, "LINE_STRIP", {"pos": coords})
    try:
        gpu.state.line_width_set(line_width)
    except Exception:
        pass
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)
    try:
        gpu.state.line_width_set(1.0)
    except Exception:
        pass


def _draw_line(shader, coords, color, line_width=2.0):
    from gpu_extras.batch import batch_for_shader

    import gpu

    batch = batch_for_shader(shader, "LINES", {"pos": coords})
    try:
        gpu.state.line_width_set(line_width)
    except Exception:
        pass
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)
    try:
        gpu.state.line_width_set(1.0)
    except Exception:
        pass


def _is_cut_tool_active(context):
    space = getattr(context, "space_data", None)
    workspace = getattr(context, "workspace", None)
    if space is None or workspace is None or getattr(space, "type", None) != "IMAGE_EDITOR":
        return False
    try:
        tool = workspace.tools.from_space_image_mode(space.mode, create=False)
    except Exception:
        return False
    return getattr(tool, "idname", "") == CUT_TOOL_ID


def _draw_cut_preview(context, region, shader, leaves):
    project = context.scene.hotspot_project
    if not project.cut_preview_active:
        return

    if not _is_cut_tool_active(context):
        properties.clear_cut_preview(project)
        return

    leaf = find_leaf_at_uv(leaves, project.cut_preview_u, project.cut_preview_v)
    if leaf is None:
        properties.clear_cut_preview(project)
        return

    b = leaf.bounds
    settings = project.settings
    color = tuple(getattr(settings, "cut_preview_color", CUT_PREVIEW_COLOR))
    width = getattr(settings, "cut_preview_width", CUT_PREVIEW_WIDTH)

    if settings.cutter_grid_enabled:
        for ratio in grid_preview_ratios(settings.cutter_grid_size):
            x = b.x0 + (b.x1 - b.x0) * ratio
            _draw_line(
                shader,
                (
                    _view_to_region(region, x, b.y0),
                    _view_to_region(region, x, b.y1),
                ),
                color,
                width,
            )
            y = b.y0 + (b.y1 - b.y0) * ratio
            _draw_line(
                shader,
                (
                    _view_to_region(region, b.x0, y),
                    _view_to_region(region, b.x1, y),
                ),
                color,
                width,
            )
        return

    orientation = choose_cut_orientation(leaf.bounds, project.cut_preview_u, project.cut_preview_v)
    cuts = max(1, min(16, settings.cutter_line_cuts))
    if cuts > 1:
        for ratio in loop_cut_preview_ratios(cuts):
            if orientation == SPLIT_VERTICAL:
                x = b.x0 + (b.x1 - b.x0) * ratio
                coords = (
                    _view_to_region(region, x, b.y0),
                    _view_to_region(region, x, b.y1),
                )
            else:
                y = b.y0 + (b.y1 - b.y0) * ratio
                coords = (
                    _view_to_region(region, b.x0, y),
                    _view_to_region(region, b.x1, y),
                )
            _draw_line(shader, coords, color, width)
        return

    ratio = cursor_split_ratio(b, orientation, project.cut_preview_u, project.cut_preview_v, settings.cutter_midpoint_snap)
    if orientation == SPLIT_VERTICAL:
        x = b.x0 + (b.x1 - b.x0) * ratio
        coords = (
            _view_to_region(region, x, b.y0),
            _view_to_region(region, x, b.y1),
        )
    else:
        y = b.y0 + (b.y1 - b.y0) * ratio
        coords = (
            _view_to_region(region, b.x0, y),
            _view_to_region(region, b.x1, y),
        )

    _draw_line(shader, coords, color, width)


def _tag_all_image_editors():
    try:
        windows = bpy.context.window_manager.windows
    except Exception:
        return

    for window in windows:
        screen = getattr(window, "screen", None)
        if screen is None:
            continue
        for area in screen.areas:
            if area.type == "IMAGE_EDITOR":
                area.tag_redraw()


def _project_from_scene(scene):
    try:
        return scene.hotspot_project if hasattr(scene, "hotspot_project") else None
    except Exception:
        return None


def _reset_scene_transient_state():
    scenes = getattr(bpy.data, "scenes", None)
    if scenes is None:
        return False
    for scene in scenes:
        project = _project_from_scene(scene)
        if project is None:
            continue
        properties.normalize_active_node(project)
        properties.clear_cut_preview(project)
        if project.nodes:
            try:
                from . import operators

                operators.mark_project_dirty(project)
            except Exception:
                project.is_dirty = True
                pass
    return True


def _reset_scene_transient_state_after_register():
    if not _reset_scene_transient_state():
        return 0.1
    _tag_all_image_editors()
    return None


@persistent
def _hotspot_undo_redo_post(_dummy):
    try:
        _reset_scene_transient_state()
        _tag_all_image_editors()
    except Exception:
        return


def _remove_matching_handler(handler_collection, function_name):
    for handler in list(handler_collection):
        if getattr(handler, "__name__", "") == function_name and "hotspot_base_map_generator" in getattr(handler, "__module__", ""):
            try:
                handler_collection.remove(handler)
            except ValueError:
                pass


def _register_app_handlers():
    for handler_collection in (bpy.app.handlers.undo_post, bpy.app.handlers.redo_post):
        _remove_matching_handler(handler_collection, "_hotspot_undo_redo_post")
        handler_collection.append(_hotspot_undo_redo_post)


def _unregister_app_handlers():
    for handler_collection in (bpy.app.handlers.undo_post, bpy.app.handlers.redo_post):
        _remove_matching_handler(handler_collection, "_hotspot_undo_redo_post")


def _draw_overlay():
    try:
        context = bpy.context
        area = context.area
        region = context.region
        scene = context.scene
        if area is None or region is None or area.type != "IMAGE_EDITOR":
            return

        project = scene.hotspot_project
        properties.normalize_active_node(project)
        if not project.nodes:
            properties.clear_cut_preview(project)
            return
        is_cut_tool_active = _is_cut_tool_active(context)
        if not is_cut_tool_active and project.cut_preview_active:
            properties.clear_cut_preview(project)
        if not project.settings.overlay_enabled:
            properties.clear_cut_preview(project)
            return

        records = properties.nodes_to_records(project)
        leaves = derive_leaf_regions(records)
        if not leaves:
            return

        shader = _get_shader()
        if shader is None:
            return

        import gpu

        gpu.state.blend_set("ALPHA")
        settings = project.settings
        border_width = settings.leaf_border_width
        regular_color = tuple(settings.leaf_border_color)
        active_color = tuple(settings.active_leaf_border_color)
        for leaf in leaves:
            b = leaf.bounds
            x0, y0 = _view_to_region(region, b.x0, b.y0)
            x1, y1 = _view_to_region(region, b.x1, b.y1)
            coords = ((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0))
            color = active_color if leaf.node_id == project.active_node_id else regular_color
            _draw_rect(shader, coords, color, border_width)
        _draw_cut_preview(context, region, shader, leaves)
        gpu.state.blend_set("NONE")
    except Exception:
        return


def register():
    global _handler
    if _handler is None:
        _handler = bpy.types.SpaceImageEditor.draw_handler_add(_draw_overlay, (), "WINDOW", "POST_PIXEL")
    _register_app_handlers()
    if not bpy.app.timers.is_registered(_reset_scene_transient_state_after_register):
        bpy.app.timers.register(_reset_scene_transient_state_after_register, first_interval=0.0)


def unregister():
    global _handler, _shader_cache
    _unregister_app_handlers()
    try:
        if bpy.app.timers.is_registered(_reset_scene_transient_state_after_register):
            bpy.app.timers.unregister(_reset_scene_transient_state_after_register)
    except Exception:
        pass
    if _handler is not None:
        bpy.types.SpaceImageEditor.draw_handler_remove(_handler, "WINDOW")
        _handler = None
    _shader_cache = None
