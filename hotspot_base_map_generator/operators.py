"""Blender operators for Hotspot Base Map Generator."""

import bpy
from bpy.props import EnumProperty, FloatProperty, IntProperty

from . import image_io, properties, tools
from .constants import (
    COLOR_MODE_RANDOM,
    SPLIT_HORIZONTAL,
    SPLIT_NONE,
    SPLIT_VERTICAL,
)
from .model.layout import (
    NodeRecord,
    build_root,
    choose_cut_orientation,
    cursor_segment_index,
    cursor_split_ratio,
    derive_leaf_regions,
    find_leaf_at_uv,
    validate_grid_dimensions,
)
from .raster import deterministic_color, render_id_pixels_from_leaves


SPLIT_ITEMS = (
    (SPLIT_HORIZONTAL, "Horizontal", "Split selected region into bottom and top halves"),
    (SPLIT_VERTICAL, "Vertical", "Split selected region into left and right halves"),
)


def project_from_context(context):
    return context.scene.hotspot_project


def image_window_region(context):
    region = getattr(context, "region", None)
    if getattr(region, "type", None) == "WINDOW" and getattr(region, "view2d", None) is not None:
        return region

    area = getattr(context, "area", None)
    if area is None:
        return None
    for candidate in area.regions:
        if candidate.type == "WINDOW" and getattr(candidate, "view2d", None) is not None:
            return candidate
    return None


def set_node_color_from_seed(node, seed, mode=COLOR_MODE_RANDOM):
    node.color = deterministic_color(node.node_id, seed, mode)


def render_project_id_map(context):
    project = project_from_context(context)
    if not project.nodes:
        raise RuntimeError("Create a hotspot canvas before rendering")

    settings = project.settings
    resolution = settings.resolution
    records = properties.nodes_to_records(project)
    leaves = derive_leaf_regions(records)
    pixels = render_id_pixels_from_leaves(
        leaves,
        resolution,
        resolution,
        seed=settings.color_seed,
        color_mode=settings.color_mode,
        background=tuple(settings.background_color),
    )

    image = image_io.ensure_image(image_io.id_image_name(context.scene), resolution, resolution)
    image_io.write_pixels(image, pixels)
    image_io.show_image_in_context(context, image)

    project.id_image_name = image.name
    project.is_dirty = False
    return image


def region_coords_to_uv(context, region_x, region_y):
    region = image_window_region(context)
    view2d = getattr(region, "view2d", None)
    if view2d is None:
        return None
    try:
        return view2d.region_to_view(region_x, region_y)
    except Exception:
        return None


def split_project_node(project, node_id, orientation, ratio=0.5, select_child_index=0):
    properties.normalize_active_node(project)
    active_index = properties.node_index_by_id(project, node_id)
    if active_index == -1:
        raise ValueError(f"Unknown region id {node_id}")
    if orientation not in {SPLIT_HORIZONTAL, SPLIT_VERTICAL}:
        raise ValueError(f"Unsupported split orientation: {orientation}")
    if not 0.001 <= ratio <= 0.999:
        raise ValueError("Split ratio must be between 0.001 and 0.999")
    if not properties.is_node_leaf(project, node_id):
        raise ValueError("Only leaf regions can be split")

    active = project.nodes[active_index]
    first_id = properties.next_project_node_id(project)
    active.split_kind = orientation
    active.split_ratio = ratio

    for child_index in range(2):
        child = properties.add_record(
            project,
            NodeRecord(
                node_id=first_id + child_index,
                parent_id=active.node_id,
                child_index=child_index,
                split_kind=SPLIT_NONE,
                split_ratio=0.5,
                color=tuple(active.color),
                label=f"Region {first_id + child_index}",
            ),
        )
        set_node_color_from_seed(child, project.settings.color_seed, project.settings.color_mode)

    project.is_dirty = True
    properties.clear_cut_preview(project)
    selected_id = first_id + max(0, min(1, select_child_index))
    properties.set_active_node(project, selected_id)
    return first_id, first_id + 1


def split_project_node_into_equal_segments(project, node_id, orientation, count):
    if count < 1:
        raise ValueError("Segment count must be at least 1")
    if count == 1:
        return [node_id]

    segment_ids = []
    current_id = node_id
    for remaining in range(count, 1, -1):
        first_child_id, second_child_id = split_project_node(project, current_id, orientation, 1.0 / remaining, 0)
        segment_ids.append(first_child_id)
        current_id = second_child_id
    segment_ids.append(current_id)
    return segment_ids


def grid_subdivide_project_node(project, node_id, rows, columns):
    validate_grid_dimensions(rows, columns)
    if not properties.is_node_leaf(project, node_id):
        raise ValueError("Only leaf regions can be grid subdivided")

    row_ids = split_project_node_into_equal_segments(project, node_id, SPLIT_HORIZONTAL, rows)
    cell_ids = []
    for row_id in row_ids:
        column_ids = split_project_node_into_equal_segments(project, row_id, SPLIT_VERTICAL, columns)
        cell_ids.extend(column_ids)

    if cell_ids:
        properties.set_active_node(project, cell_ids[0])
    project.is_dirty = True
    properties.clear_cut_preview(project)
    return cell_ids


def cut_project_at_uv(project, u, v):
    records = properties.nodes_to_records(project)
    leaves = derive_leaf_regions(records)
    leaf = find_leaf_at_uv(leaves, u, v)
    if leaf is None:
        raise ValueError("Cursor is outside the hotspot canvas")

    settings = project.settings
    if settings.cutter_grid_enabled:
        size = max(2, min(16, settings.cutter_grid_size))
        cell_ids = grid_subdivide_project_node(project, leaf.node_id, size, size)
        return leaf, f"{size}x{size} grid", cell_ids

    orientation = choose_cut_orientation(leaf.bounds, u, v)
    cuts = max(1, min(16, settings.cutter_line_cuts))
    if cuts > 1:
        segment_count = cuts + 1
        segment_ids = split_project_node_into_equal_segments(project, leaf.node_id, orientation, segment_count)
        selected_index = cursor_segment_index(leaf.bounds, orientation, u, v, segment_count)
        properties.set_active_node(project, segment_ids[selected_index])
        project.is_dirty = True
        properties.clear_cut_preview(project)
        return leaf, f"{orientation.lower()} {cuts} cuts", segment_ids

    ratio = cursor_split_ratio(leaf.bounds, orientation, u, v, settings.cutter_midpoint_snap)
    if orientation == SPLIT_VERTICAL:
        split_x = leaf.bounds.x0 + (leaf.bounds.x1 - leaf.bounds.x0) * ratio
        select_child_index = 0 if u < split_x else 1
    else:
        split_y = leaf.bounds.y0 + (leaf.bounds.y1 - leaf.bounds.y0) * ratio
        select_child_index = 0 if v < split_y else 1

    children = split_project_node(project, leaf.node_id, orientation, ratio, select_child_index)
    return leaf, f"{orientation.lower()} at {ratio:.1%}", children


def set_cut_preview_from_uv(project, u, v):
    if not project.nodes:
        properties.clear_cut_preview(project)
        return None

    records = properties.nodes_to_records(project)
    leaves = derive_leaf_regions(records)
    leaf = find_leaf_at_uv(leaves, u, v)
    if leaf is None:
        properties.clear_cut_preview(project)
        return None

    project.cut_preview_u = u
    project.cut_preview_v = v
    project.cut_preview_active = True
    return leaf


def tag_hotspot_areas_for_redraw(context):
    screen = getattr(context, "screen", None)
    if screen is None:
        return
    for area in screen.areas:
        if area.type == "IMAGE_EDITOR":
            area.tag_redraw()


class HOTSPOT_OT_new_canvas(bpy.types.Operator):
    bl_idname = "hotspot.new_canvas"
    bl_label = "New Hotspot Canvas"
    bl_description = "Create a new one-region hotspot canvas"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        project = project_from_context(context)
        project.nodes.clear()

        root = build_root()[0]
        node = properties.add_record(project, root)
        set_node_color_from_seed(node, project.settings.color_seed, project.settings.color_mode)

        project.id_image_name = ""
        project.is_dirty = True
        properties.set_active_node(project, node.node_id)
        self.report({"INFO"}, "Created hotspot canvas")
        properties.clear_cut_preview(project)
        tag_hotspot_areas_for_redraw(context)
        return {"FINISHED"}


class HOTSPOT_OT_select_region(bpy.types.Operator):
    bl_idname = "hotspot.select_region"
    bl_label = "Select Hotspot Region"
    bl_description = "Select a hotspot region by node id"
    bl_options = {"REGISTER", "UNDO"}

    node_id: IntProperty(name="Node ID", default=-1)

    def execute(self, context):
        project = project_from_context(context)
        if properties.node_index_by_id(project, self.node_id) == -1:
            self.report({"WARNING"}, f"Unknown region id {self.node_id}")
            return {"CANCELLED"}
        properties.set_active_node(project, self.node_id)
        properties.clear_cut_preview(project)
        tag_hotspot_areas_for_redraw(context)
        return {"FINISHED"}


class HOTSPOT_OT_split_region(bpy.types.Operator):
    bl_idname = "hotspot.split_region"
    bl_label = "Split Hotspot Region"
    bl_description = "Split the selected leaf region"
    bl_options = {"REGISTER", "UNDO"}

    orientation: EnumProperty(name="Orientation", items=SPLIT_ITEMS, default=SPLIT_VERTICAL)
    ratio: FloatProperty(name="Ratio", default=0.5, min=0.001, max=0.999, subtype="PERCENTAGE")

    @classmethod
    def poll(cls, context):
        if not hasattr(context.scene, "hotspot_project"):
            cls.poll_message_set("Hotspot project data is unavailable")
            return False
        project = project_from_context(context)
        if project.active_node_id == -1:
            cls.poll_message_set("Select a leaf region before splitting")
            return False
        if not properties.is_node_leaf(project, project.active_node_id):
            cls.poll_message_set("Only leaf regions can be split")
            return False
        return True

    def execute(self, context):
        project = project_from_context(context)
        active = properties.active_node(project)
        if active is None:
            self.report({"WARNING"}, "No active region")
            return {"CANCELLED"}
        if not properties.is_node_leaf(project, active.node_id):
            self.report({"WARNING"}, "Only leaf regions can be split")
            return {"CANCELLED"}

        split_project_node(project, active.node_id, self.orientation, self.ratio, 0)
        self.report({"INFO"}, f"Split region {active.node_id} at {self.ratio:.1%}; ID map needs regeneration")
        tag_hotspot_areas_for_redraw(context)
        return {"FINISHED"}


class HOTSPOT_OT_grid_subdivide_region(bpy.types.Operator):
    bl_idname = "hotspot.grid_subdivide_region"
    bl_label = "Grid Subdivide Region"
    bl_description = "Subdivide the selected leaf into equal rows and columns"
    bl_options = {"REGISTER", "UNDO"}

    rows: IntProperty(name="Rows", default=2, min=1, max=16)
    columns: IntProperty(name="Columns", default=2, min=1, max=16)

    @classmethod
    def poll(cls, context):
        if not hasattr(context.scene, "hotspot_project"):
            cls.poll_message_set("Hotspot project data is unavailable")
            return False
        project = project_from_context(context)
        if project.active_node_id == -1:
            cls.poll_message_set("Select a leaf region before grid subdivision")
            return False
        if not properties.is_node_leaf(project, project.active_node_id):
            cls.poll_message_set("Only leaf regions can be grid subdivided")
            return False
        return True

    def execute(self, context):
        project = project_from_context(context)
        active = properties.active_node(project)
        if active is None:
            self.report({"WARNING"}, "No active region")
            return {"CANCELLED"}

        active_id = active.node_id
        try:
            cell_ids = grid_subdivide_project_node(project, active_id, self.rows, self.columns)
        except Exception as exc:
            self.report({"WARNING"}, str(exc))
            return {"CANCELLED"}

        self.report({"INFO"}, f"Grid subdivided region {active_id} into {len(cell_ids)} cells; ID map needs regeneration")
        tag_hotspot_areas_for_redraw(context)
        return {"FINISHED"}


class HOTSPOT_OT_cut_region_at_cursor(bpy.types.Operator):
    bl_idname = "hotspot.cut_region_at_cursor"
    bl_label = "Cut Hotspot Region"
    bl_description = "Cut the hotspot leaf under the cursor"
    bl_options = {"REGISTER", "UNDO"}

    region_x: FloatProperty(name="Region X", default=-1.0, options={"HIDDEN"})
    region_y: FloatProperty(name="Region Y", default=-1.0, options={"HIDDEN"})

    @classmethod
    def poll(cls, context):
        if getattr(context.area, "type", None) != "IMAGE_EDITOR":
            cls.poll_message_set("Use the cutter in the Image Editor")
            return False
        if not hasattr(context.scene, "hotspot_project"):
            cls.poll_message_set("Hotspot project data is unavailable")
            return False
        if not context.scene.hotspot_project.nodes:
            cls.poll_message_set("Create a hotspot canvas before cutting")
            return False
        return True

    def invoke(self, context, event):
        self.region_x = event.mouse_region_x
        self.region_y = event.mouse_region_y
        return self.execute(context)

    def execute(self, context):
        uv = region_coords_to_uv(context, self.region_x, self.region_y)
        if uv is None:
            self.report({"WARNING"}, "Could not read Image Editor cursor position")
            return {"CANCELLED"}

        project = project_from_context(context)
        try:
            leaf, action, _children = cut_project_at_uv(project, uv[0], uv[1])
        except Exception as exc:
            self.report({"WARNING"}, str(exc))
            properties.clear_cut_preview(project)
            tag_hotspot_areas_for_redraw(context)
            return {"CANCELLED"}

        self.report({"INFO"}, f"Cut region {leaf.node_id} {action}; ID map needs regeneration")
        properties.clear_cut_preview(project)
        tag_hotspot_areas_for_redraw(context)
        return {"FINISHED"}


class HOTSPOT_OT_update_cut_preview(bpy.types.Operator):
    bl_idname = "hotspot.update_cut_preview"
    bl_label = "Update Hotspot Cut Preview"
    bl_description = "Update the hotspot cutter hover preview"
    bl_options = {"INTERNAL"}

    @classmethod
    def poll(cls, context):
        if getattr(context.area, "type", None) != "IMAGE_EDITOR":
            return False
        if not hasattr(context.scene, "hotspot_project"):
            return False
        if not context.scene.hotspot_project.nodes:
            return False
        return True

    def invoke(self, context, event):
        uv = region_coords_to_uv(context, event.mouse_region_x, event.mouse_region_y)
        project = project_from_context(context)
        if uv is None:
            properties.clear_cut_preview(project)
        else:
            set_cut_preview_from_uv(project, uv[0], uv[1])
        tools.update_status_text(context, True)
        tag_hotspot_areas_for_redraw(context)
        return {"FINISHED"}


class HOTSPOT_OT_toggle_midpoint_snap(bpy.types.Operator):
    bl_idname = "hotspot.toggle_midpoint_snap"
    bl_label = "Toggle Midpoint Snap"
    bl_description = "Toggle whether the cutter snaps line cuts to the hovered leaf midpoint"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return hasattr(context.scene, "hotspot_project")

    def execute(self, context):
        settings = project_from_context(context).settings
        settings.cutter_midpoint_snap = not settings.cutter_midpoint_snap
        state = "on" if settings.cutter_midpoint_snap else "off"
        tools.update_status_text(context, True)
        tag_hotspot_areas_for_redraw(context)
        self.report({"INFO"}, f"Midpoint snap {state}")
        return {"FINISHED"}


class HOTSPOT_OT_toggle_grid_cut(bpy.types.Operator):
    bl_idname = "hotspot.toggle_grid_cut"
    bl_label = "Toggle Grid Cut"
    bl_description = "Toggle square grid cutter mode"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return hasattr(context.scene, "hotspot_project")

    def execute(self, context):
        settings = project_from_context(context).settings
        settings.cutter_grid_enabled = not settings.cutter_grid_enabled
        state = "on" if settings.cutter_grid_enabled else "off"
        tools.update_status_text(context, True)
        tag_hotspot_areas_for_redraw(context)
        self.report({"INFO"}, f"Grid cut {state}")
        return {"FINISHED"}


class HOTSPOT_OT_adjust_grid_size(bpy.types.Operator):
    bl_idname = "hotspot.adjust_grid_size"
    bl_label = "Adjust Cutter Amount"
    bl_description = "Adjust loop cut count in line mode or square grid size in grid mode"
    bl_options = {"REGISTER"}

    delta: IntProperty(name="Delta", default=1, min=-16, max=16)

    @classmethod
    def poll(cls, context):
        return hasattr(context.scene, "hotspot_project")

    def execute(self, context):
        settings = project_from_context(context).settings
        if settings.cutter_grid_enabled:
            settings.cutter_grid_size = max(2, min(16, settings.cutter_grid_size + self.delta))
            message = f"Grid cut {settings.cutter_grid_size}x{settings.cutter_grid_size}"
        else:
            settings.cutter_line_cuts = max(1, min(16, settings.cutter_line_cuts + self.delta))
            message = f"Loop cuts {settings.cutter_line_cuts}"
        tools.update_status_text(context, True)
        tag_hotspot_areas_for_redraw(context)
        self.report({"INFO"}, message)
        return {"FINISHED"}


class HOTSPOT_OT_activate_cut_tool(bpy.types.Operator):
    bl_idname = "hotspot.activate_cut_tool"
    bl_label = "Activate Cutter Tool"
    bl_description = "Switch the Image Editor to Paint mode and activate the Hotspot Cut toolbar tool"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        if getattr(context.area, "type", None) != "IMAGE_EDITOR":
            cls.poll_message_set("Use this from the Image Editor")
            return False
        if not hasattr(context.scene, "hotspot_project"):
            cls.poll_message_set("Hotspot project data is unavailable")
            return False
        if not context.scene.hotspot_project.nodes:
            cls.poll_message_set("Create a hotspot canvas before activating the cutter")
            return False
        return True

    def execute(self, context):
        if not tools.ensure_registered():
            self.report({"ERROR"}, "Hotspot Cut tool is not available in the Image Editor Paint toolbar")
            return {"CANCELLED"}

        space = getattr(context, "space_data", None)
        if space is not None and getattr(space, "type", None) == "IMAGE_EDITOR":
            try:
                space.mode = "PAINT"
            except Exception:
                pass

        try:
            bpy.ops.wm.tool_set_by_id(name="hotspot.region_cutter")
        except Exception as exc:
            self.report({"ERROR"}, f"Hotspot Cut tool is not registered: {exc}")
            return {"CANCELLED"}

        tools.set_status_text(context)
        properties.clear_cut_preview(project_from_context(context))
        tag_hotspot_areas_for_redraw(context)
        self.report({"INFO"}, "Activated Hotspot Cut tool")
        return {"FINISHED"}


class HOTSPOT_OT_render_map(bpy.types.Operator):
    bl_idname = "hotspot.render_map"
    bl_label = "Render ID Map"
    bl_description = "Generate the hotspot ID map image"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        if not hasattr(context.scene, "hotspot_project"):
            cls.poll_message_set("Hotspot project data is unavailable")
            return False
        if not context.scene.hotspot_project.nodes:
            cls.poll_message_set("Create a hotspot canvas before rendering")
            return False
        return True

    def execute(self, context):
        try:
            image = render_project_id_map(context)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        properties.clear_cut_preview(project_from_context(context))
        tag_hotspot_areas_for_redraw(context)
        self.report({"INFO"}, f"Rendered {image.name}")
        return {"FINISHED"}


class HOTSPOT_OT_export_maps(bpy.types.Operator):
    bl_idname = "hotspot.export_maps"
    bl_label = "Export ID Map"
    bl_description = "Export the hotspot ID map as PNG"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        if not hasattr(context.scene, "hotspot_project"):
            cls.poll_message_set("Hotspot project data is unavailable")
            return False
        if not context.scene.hotspot_project.nodes:
            cls.poll_message_set("Create a hotspot canvas before exporting")
            return False
        return True

    def execute(self, context):
        project = project_from_context(context)
        image = bpy.data.images.get(project.id_image_name)
        regenerated = False
        if image is None or project.is_dirty:
            try:
                image = render_project_id_map(context)
                regenerated = True
            except Exception as exc:
                self.report({"ERROR"}, str(exc))
                return {"CANCELLED"}

        path = image_io.export_image_png(
            image,
            project.settings.export_directory,
            project.settings.export_stem,
            "ID",
        )
        properties.clear_cut_preview(project)
        tag_hotspot_areas_for_redraw(context)
        prefix = "Regenerated and exported" if regenerated else "Exported"
        self.report({"INFO"}, f"{prefix} {path}")
        return {"FINISHED"}


classes = (
    HOTSPOT_OT_new_canvas,
    HOTSPOT_OT_select_region,
    HOTSPOT_OT_split_region,
    HOTSPOT_OT_grid_subdivide_region,
    HOTSPOT_OT_cut_region_at_cursor,
    HOTSPOT_OT_update_cut_preview,
    HOTSPOT_OT_toggle_midpoint_snap,
    HOTSPOT_OT_toggle_grid_cut,
    HOTSPOT_OT_adjust_grid_size,
    HOTSPOT_OT_activate_cut_tool,
    HOTSPOT_OT_render_map,
    HOTSPOT_OT_export_maps,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
