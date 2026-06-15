"""Blender scene properties for Hotspot Base Map Generator."""

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    FloatVectorProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)

from .constants import (
    COLOR_MODE_GRAYSCALE,
    COLOR_MODE_RANDOM,
    COLOR_MODE_STORED,
    SPLIT_NONE,
)
from .model.layout import NodeRecord


def _active_node_index_update(self, _context):
    if 0 <= self.active_node_index < len(self.nodes):
        self.active_node_id = self.nodes[self.active_node_index].node_id
    else:
        self.active_node_id = -1


COLOR_MODE_ITEMS = (
    (COLOR_MODE_RANDOM, "Deterministic Colors", "Assign stable seeded colors per region"),
    (COLOR_MODE_GRAYSCALE, "Sequential Grayscale", "Assign stable grayscale values per region"),
    (COLOR_MODE_STORED, "Stored Region Colors", "Use each region's editable stored color"),
)


class HotspotNode(bpy.types.PropertyGroup):
    node_id: IntProperty(name="Node ID", default=0, min=0)
    parent_id: IntProperty(name="Parent ID", default=-1)
    child_index: IntProperty(name="Child Index", default=0, min=0)
    split_kind: EnumProperty(
        name="Split",
        items=(
            (SPLIT_NONE, "None", "Leaf region"),
            ("HORIZONTAL", "Horizontal", "Split into bottom and top child regions"),
            ("VERTICAL", "Vertical", "Split into left and right child regions"),
        ),
        default=SPLIT_NONE,
    )
    split_ratio: FloatProperty(name="Split Ratio", default=0.5, min=0.001, max=0.999)
    color: FloatVectorProperty(
        name="Color",
        subtype="COLOR",
        size=4,
        min=0.0,
        max=1.0,
        default=(1.0, 1.0, 1.0, 1.0),
    )
    label: StringProperty(name="Label", default="")


class HotspotCanvasSettings(bpy.types.PropertyGroup):
    resolution: IntProperty(name="Resolution", default=2048, min=16, max=8192, subtype="PIXEL")
    color_seed: IntProperty(name="Color Seed", default=1337, min=0)
    color_mode: EnumProperty(name="ID Color Mode", items=COLOR_MODE_ITEMS, default=COLOR_MODE_RANDOM)
    background_color: FloatVectorProperty(
        name="Background",
        subtype="COLOR",
        size=4,
        min=0.0,
        max=1.0,
        default=(0.0, 0.0, 0.0, 1.0),
    )
    split_ratio: FloatProperty(
        name="Split Ratio",
        default=0.5,
        min=0.001,
        max=0.999,
        subtype="PERCENTAGE",
    )
    grid_rows: IntProperty(name="Rows", default=2, min=1, max=16)
    grid_columns: IntProperty(name="Columns", default=2, min=1, max=16)
    cutter_midpoint_snap: BoolProperty(name="Midpoint Snap", default=True)
    cutter_grid_enabled: BoolProperty(name="Grid Cut", default=False)
    cutter_line_cuts: IntProperty(name="Loop Cuts", default=1, min=1, max=16)
    cutter_grid_size: IntProperty(name="Grid Size", default=2, min=2, max=16)
    overlay_enabled: BoolProperty(name="Overlay", default=True)
    leaf_border_width: FloatProperty(
        name="Leaf Border Width",
        default=1.0,
        min=1.0,
        max=12.0,
        subtype="PIXEL",
    )
    leaf_border_color: FloatVectorProperty(
        name="Leaf Border Color",
        subtype="COLOR",
        size=4,
        min=0.0,
        max=1.0,
        default=(0.2, 0.9, 1.0, 0.55),
    )
    active_leaf_border_color: FloatVectorProperty(
        name="Active Leaf Border",
        subtype="COLOR",
        size=4,
        min=0.0,
        max=1.0,
        default=(1.0, 0.82, 0.18, 0.85),
    )
    cut_preview_width: FloatProperty(
        name="Cutter Line Width",
        default=2.0,
        min=1.0,
        max=12.0,
        subtype="PIXEL",
    )
    cut_preview_color: FloatVectorProperty(
        name="Cutter Line Color",
        subtype="COLOR",
        size=4,
        min=0.0,
        max=1.0,
        default=(0.1, 0.42, 1.0, 0.95),
    )
    export_directory: StringProperty(name="Directory", subtype="DIR_PATH", default="//")
    export_stem: StringProperty(name="Filename Stem", default="hotspot_base_map")


class HotspotProject(bpy.types.PropertyGroup):
    nodes: CollectionProperty(type=HotspotNode)
    active_node_id: IntProperty(name="Active Node ID", default=-1)
    active_node_index: IntProperty(
        name="Active Region",
        default=-1,
        min=-1,
        update=_active_node_index_update,
    )
    id_image_name: StringProperty(name="ID Image", default="")
    is_dirty: BoolProperty(name="Needs Regeneration", default=True)
    cut_preview_active: BoolProperty(name="Cut Preview Active", default=False, options={"HIDDEN"})
    cut_preview_u: FloatProperty(name="Cut Preview U", default=0.0, options={"HIDDEN"})
    cut_preview_v: FloatProperty(name="Cut Preview V", default=0.0, options={"HIDDEN"})
    settings: PointerProperty(type=HotspotCanvasSettings)


def node_index_by_id(project, node_id):
    for index, node in enumerate(project.nodes):
        if node.node_id == node_id:
            return index
    return -1


def active_node(project):
    index = node_index_by_id(project, project.active_node_id)
    if index == -1:
        return None
    return project.nodes[index]


def is_node_leaf(project, node_id):
    if node_index_by_id(project, node_id) == -1:
        return False
    return not any(node.parent_id == node_id for node in project.nodes)


def next_project_node_id(project):
    return max((node.node_id for node in project.nodes), default=0) + 1


def set_active_node(project, node_id):
    index = node_index_by_id(project, node_id)
    project.active_node_id = node_id if index != -1 else -1
    if project.active_node_index != index:
        project.active_node_index = index


def normalize_active_node(project):
    if not project.nodes:
        project.active_node_id = -1
        if project.active_node_index != -1:
            project.active_node_index = -1
        return None

    index = node_index_by_id(project, project.active_node_id)
    if index != -1:
        if project.active_node_index != index:
            project.active_node_index = index
        return project.nodes[index]

    if 0 <= project.active_node_index < len(project.nodes):
        project.active_node_id = project.nodes[project.active_node_index].node_id
        return project.nodes[project.active_node_index]

    fallback = next((node for node in project.nodes if is_node_leaf(project, node.node_id)), project.nodes[0])
    set_active_node(project, fallback.node_id)
    return fallback


def clear_cut_preview(project):
    project.cut_preview_active = False
    project.cut_preview_u = 0.0
    project.cut_preview_v = 0.0


def nodes_to_records(project):
    records = []
    for node in project.nodes:
        records.append(
            NodeRecord(
                node_id=node.node_id,
                parent_id=node.parent_id,
                child_index=node.child_index,
                split_kind=node.split_kind,
                split_ratio=node.split_ratio,
                color=tuple(node.color),
                label=node.label,
            )
        )
    return records


def add_record(project, record):
    node = project.nodes.add()
    node.node_id = record.node_id
    node.parent_id = record.parent_id
    node.child_index = record.child_index
    node.split_kind = record.split_kind
    node.split_ratio = record.split_ratio
    node.color = record.color
    node.label = record.label
    return node


classes = (
    HotspotNode,
    HotspotCanvasSettings,
    HotspotProject,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.hotspot_project = PointerProperty(type=HotspotProject)


def unregister():
    if hasattr(bpy.types.Scene, "hotspot_project"):
        del bpy.types.Scene.hotspot_project
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
