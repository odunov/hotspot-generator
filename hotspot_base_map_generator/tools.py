"""Toolbar tools for Hotspot Base Map Generator."""

import time

import bpy
from bpy.types import WorkSpaceTool

TOOL_ID = "hotspot.region_cutter"
TOOL_CONTEXT_MODE = "PAINT"
_status_text_active = False
_status_timer_running = False
_status_text_last_refresh = 0.0
_STATUS_TIMEOUT_SECONDS = 1.5


class HOTSPOT_WST_region_cutter(WorkSpaceTool):
    bl_space_type = "IMAGE_EDITOR"
    bl_context_mode = TOOL_CONTEXT_MODE
    bl_idname = TOOL_ID
    bl_label = "Hotspot Cut"
    bl_description = "Cut hotspot leaf regions with line and grid subdivisions"
    bl_icon = "ops.generic.select_box"
    bl_widget = None
    bl_keymap = (
        (
            "hotspot.update_cut_preview",
            {"type": "MOUSEMOVE", "value": "ANY", "any": True},
            None,
        ),
        (
            "hotspot.cut_region_at_cursor",
            {"type": "LEFTMOUSE", "value": "PRESS"},
            None,
        ),
        (
            "hotspot.toggle_midpoint_snap",
            {"type": "M", "value": "PRESS"},
            None,
        ),
        (
            "hotspot.toggle_grid_cut",
            {"type": "G", "value": "PRESS"},
            None,
        ),
        (
            "hotspot.adjust_grid_size",
            {"type": "WHEELUPMOUSE", "value": "PRESS", "shift": True},
            {"properties": [("delta", 1)]},
        ),
        (
            "hotspot.adjust_grid_size",
            {"type": "WHEELDOWNMOUSE", "value": "PRESS", "shift": True},
            {"properties": [("delta", -1)]},
        ),
    )


def _keymap_name():
    tool_def = getattr(HOTSPOT_WST_region_cutter, "_bl_tool", None)
    keymap = getattr(tool_def, "keymap", None)
    if keymap:
        return keymap[0]
    return "Image Editor Tool: Paint, Hotspot Cut"


def _keymap_from_context(context):
    wm = getattr(context, "window_manager", None)
    if wm is None:
        return None

    keymap_name = _keymap_name()
    for keyconfig in (wm.keyconfigs.addon, wm.keyconfigs.user, wm.keyconfigs.default):
        if keyconfig is None:
            continue
        keymap = keyconfig.keymaps.get(keymap_name)
        if keymap is not None:
            return keymap
    return None


def _find_keymap_item(keymap, operator_id, delta=None):
    if keymap is None:
        return None

    for item in keymap.keymap_items:
        if item.idname != operator_id:
            continue
        if delta is None:
            return item
        try:
            if item.properties.delta == delta:
                return item
        except Exception:
            pass
    return None


def _draw_status_item(layout, keymap, operator_id, text, delta=None, fallback=""):
    item = _find_keymap_item(keymap, operator_id, delta)
    row = layout.row(align=True)
    if item is None:
        row.label(text=fallback or text)
    else:
        row.template_event_from_keymap_item(item, text=text)


def _draw_amount_status_item(layout, text):
    row = layout.row(align=True)
    row.label(text="", icon="EVENT_SHIFT")
    row.label(text="", icon="MOUSE_MMB_SCROLL")
    row.label(text=text)


def _draw_status_text(self, context):
    layout = self.layout
    keymap = _keymap_from_context(context)
    settings = getattr(getattr(context.scene, "hotspot_project", None), "settings", None)
    snap_text = "Snap On" if settings is None or settings.cutter_midpoint_snap else "Snap Off"
    if settings is None or not settings.cutter_grid_enabled:
        grid_text = "Grid Off"
        amount_text = f"Cuts {settings.cutter_line_cuts if settings is not None else 1}"
    else:
        grid_text = f"Grid {settings.cutter_grid_size}x{settings.cutter_grid_size}"
        amount_text = f"Grid {settings.cutter_grid_size}x{settings.cutter_grid_size}"

    flow = layout.grid_flow(columns=4, align=True, row_major=True)
    _draw_status_item(flow, keymap, "hotspot.cut_region_at_cursor", "Cut", fallback="LMB Cut")
    _draw_status_item(flow, keymap, "hotspot.toggle_midpoint_snap", snap_text, fallback=f"M {snap_text}")
    _draw_status_item(flow, keymap, "hotspot.toggle_grid_cut", grid_text, fallback=f"G {grid_text}")
    _draw_amount_status_item(flow, amount_text)

    layout.separator_spacer()
    layout.template_reports_banner()
    layout.template_running_jobs()
    layout.separator_spacer()
    row = layout.row()
    row.alignment = "RIGHT"
    layout.template_status_info()


def _context_is_image_cutter(context):
    area = getattr(context, "area", None)
    space = getattr(context, "space_data", None)
    workspace = getattr(context, "workspace", None)
    if area is not None and getattr(area, "type", None) != "IMAGE_EDITOR":
        return False
    if space is None or workspace is None or getattr(space, "type", None) != "IMAGE_EDITOR":
        return False
    try:
        tool = workspace.tools.from_space_image_mode(space.mode, create=False)
    except Exception:
        return False
    return getattr(tool, "idname", "") == TOOL_ID


def _status_timer():
    global _status_timer_running, _status_text_last_refresh
    if not _status_text_active:
        _status_timer_running = False
        return None

    if _context_is_image_cutter(bpy.context):
        _status_text_last_refresh = time.monotonic()
        return 0.25

    if time.monotonic() - _status_text_last_refresh >= _STATUS_TIMEOUT_SECONDS:
        clear_status_text(bpy.context)
        _status_timer_running = False
        return None
    return 0.25


def _ensure_status_timer():
    global _status_timer_running
    if _status_timer_running:
        return
    _status_timer_running = True
    try:
        bpy.app.timers.register(_status_timer, first_interval=0.25)
    except Exception:
        _status_timer_running = False


def set_status_text(context):
    global _status_text_active, _status_text_last_refresh
    if not _context_is_image_cutter(context):
        return
    workspace = getattr(context, "workspace", None)
    if workspace is None:
        return
    _status_text_last_refresh = time.monotonic()
    workspace.status_text_set(_draw_status_text)
    _status_text_active = True
    _ensure_status_timer()


def clear_status_text(context):
    global _status_text_active
    if not _status_text_active:
        return
    workspace = getattr(context, "workspace", None)
    if workspace is None:
        return
    workspace.status_text_set(None)
    _status_text_active = False


def update_status_text(context, active):
    if active:
        set_status_text(context)
    else:
        clear_status_text(context)


def _tool_ids():
    try:
        from bl_ui.space_toolsystem_toolbar import IMAGE_PT_tools_active
    except Exception:
        return []

    tools = IMAGE_PT_tools_active._tools.get(TOOL_CONTEXT_MODE, ())
    ids = []
    for item in tools:
        if item is None:
            continue
        if type(item) is tuple:
            ids.extend(getattr(child, "idname", "") for child in item)
        else:
            ids.append(getattr(item, "idname", ""))
    return ids


def is_registered():
    return TOOL_ID in _tool_ids()


def ensure_registered():
    try:
        bpy.utils.unregister_tool(HOTSPOT_WST_region_cutter)
    except Exception:
        pass
    try:
        bpy.utils.register_tool(HOTSPOT_WST_region_cutter, after={"builtin_brush.mask"}, separator=True)
    except Exception as exc:
        print(f"Hotspot Cut toolbar registration failed: {exc}")
        return False
    return is_registered()


def _tag_image_editors_for_redraw():
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

def register():
    ensure_registered()


def unregister():
    clear_status_text(bpy.context)
    try:
        bpy.utils.unregister_tool(HOTSPOT_WST_region_cutter)
    except Exception:
        pass
