"""Image Editor UI for Hotspot Base Map Generator."""

import bpy

from . import properties
from .constants import SPLIT_HORIZONTAL, SPLIT_VERTICAL


class HOTSPOT_UL_nodes(bpy.types.UIList):
    def draw_item(self, _context, layout, data, item, _icon, _active_data, _active_propname, _index):
        project = data
        is_leaf = properties.is_node_leaf(project, item.node_id)
        status = "Leaf" if is_leaf else item.split_kind.title()
        label = item.label or f"Region {item.node_id}"
        layout.label(text=f"{item.node_id}: {label} [{status}]")


class HOTSPOT_PT_canvas(bpy.types.Panel):
    bl_space_type = "IMAGE_EDITOR"
    bl_region_type = "UI"
    bl_category = "Hotspot"
    bl_label = "Canvas"

    def draw(self, context):
        project = context.scene.hotspot_project
        layout = self.layout

        layout.operator("hotspot.new_canvas")
        layout.separator()

        settings = project.settings
        layout.prop(settings, "resolution")
        layout.prop(settings, "color_seed")
        layout.prop(settings, "color_mode")
        layout.prop(settings, "background_color")

        row = layout.row(align=True)
        row.enabled = bool(project.nodes)
        row.operator("hotspot.render_map")
        row.operator("hotspot.export_maps")

        if project.id_image_name:
            layout.label(text=f"Image: {project.id_image_name}")
        if project.nodes and project.is_dirty:
            layout.label(text="Needs regeneration")


class HOTSPOT_PT_cutter(bpy.types.Panel):
    bl_space_type = "IMAGE_EDITOR"
    bl_region_type = "UI"
    bl_category = "Hotspot"
    bl_label = "Cutter"

    def draw(self, context):
        project = context.scene.hotspot_project
        settings = project.settings
        layout = self.layout

        row = layout.row()
        row.enabled = bool(project.nodes)
        row.operator("hotspot.activate_cut_tool")
        layout.prop(settings, "cutter_midpoint_snap")
        layout.prop(settings, "cutter_grid_enabled")
        loop_row = layout.row()
        loop_row.enabled = not settings.cutter_grid_enabled
        loop_row.prop(settings, "cutter_line_cuts")
        grid_row = layout.row()
        grid_row.enabled = settings.cutter_grid_enabled
        grid_row.prop(settings, "cutter_grid_size")


class HOTSPOT_PT_region(bpy.types.Panel):
    bl_space_type = "IMAGE_EDITOR"
    bl_region_type = "UI"
    bl_category = "Hotspot"
    bl_label = "Region"

    def draw(self, context):
        project = context.scene.hotspot_project
        layout = self.layout

        if not project.nodes:
            layout.label(text="No canvas")
            return

        layout.template_list(
            "HOTSPOT_UL_nodes",
            "",
            project,
            "nodes",
            project,
            "active_node_index",
            rows=6,
        )

        active = properties.active_node(project)
        if active is None:
            layout.label(text="No active region")
            return

        layout.separator()
        layout.prop(active, "label")
        layout.prop(active, "color")

        is_leaf = properties.is_node_leaf(project, active.node_id)
        settings = project.settings
        split_box = layout.box()
        split_box.enabled = is_leaf
        split_box.prop(settings, "split_ratio")
        row = split_box.row(align=True)
        op = row.operator("hotspot.split_region", text="Split H")
        op.orientation = SPLIT_HORIZONTAL
        op.ratio = settings.split_ratio
        op = row.operator("hotspot.split_region", text="Split V")
        op.orientation = SPLIT_VERTICAL
        op.ratio = settings.split_ratio

        grid_box = layout.box()
        grid_box.enabled = is_leaf
        grid_row = grid_box.row(align=True)
        grid_row.prop(settings, "grid_rows")
        grid_row.prop(settings, "grid_columns")
        grid_buttons = grid_box.row(align=True)
        op = grid_buttons.operator("hotspot.grid_subdivide_region", text="2x2")
        op.rows = 2
        op.columns = 2
        op = grid_buttons.operator("hotspot.grid_subdivide_region", text="Grid")
        op.rows = settings.grid_rows
        op.columns = settings.grid_columns
        if not is_leaf:
            split_box.label(text="Internal region")
            grid_box.label(text="Internal region")


class HOTSPOT_PT_overlay(bpy.types.Panel):
    bl_space_type = "IMAGE_EDITOR"
    bl_region_type = "UI"
    bl_category = "Hotspot"
    bl_label = "Overlay"

    def draw(self, context):
        project = context.scene.hotspot_project
        settings = project.settings
        layout = self.layout

        layout.prop(settings, "overlay_enabled")
        column = layout.column()
        column.enabled = settings.overlay_enabled
        column.prop(settings, "leaf_border_width")
        column.prop(settings, "leaf_border_color")
        column.prop(settings, "active_leaf_border_color")
        column.separator()
        column.prop(settings, "cut_preview_width")
        column.prop(settings, "cut_preview_color")


class HOTSPOT_PT_export(bpy.types.Panel):
    bl_space_type = "IMAGE_EDITOR"
    bl_region_type = "UI"
    bl_category = "Hotspot"
    bl_label = "Export"

    def draw(self, context):
        project = context.scene.hotspot_project
        settings = project.settings
        layout = self.layout

        layout.prop(settings, "export_directory")
        layout.prop(settings, "export_stem")
        row = layout.row()
        row.enabled = bool(project.nodes)
        row.operator("hotspot.export_maps")


classes = (
    HOTSPOT_UL_nodes,
    HOTSPOT_PT_canvas,
    HOTSPOT_PT_cutter,
    HOTSPOT_PT_region,
    HOTSPOT_PT_overlay,
    HOTSPOT_PT_export,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
