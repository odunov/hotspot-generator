"""Blender operators for Hotspot Base Map Generator."""

import time

import bpy
from bpy.props import EnumProperty, FloatProperty, IntProperty, StringProperty

from . import image_io, properties, tools
from .constants import (
    COLOR_MODE_RANDOM,
    HEIGHT_DERIVED_MAP_KEYS,
    MAP_EXPORT_ATTRS,
    MAP_IMAGE_ATTRS,
    MAP_KEYS,
    MAP_SUFFIXES,
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
from .raster import (
    deterministic_color,
    render_ao_pixels_from_height,
    render_curvature_pixels_from_height,
    render_edge_pixels_from_leaves,
    render_height_pixels_from_values,
    render_height_values_from_leaves,
    render_id_pixels_from_leaves,
    render_mask_pixels_from_leaves,
    render_normal_pixels_from_height,
)


SPLIT_ITEMS = (
    (SPLIT_HORIZONTAL, "Horizontal", "Split selected region into bottom and top halves"),
    (SPLIT_VERTICAL, "Vertical", "Split selected region into left and right halves"),
)

_AUTO_PREVIEW_DELAY = 0.025
_auto_preview_scenes = set()
_auto_preview_scheduled_at = {}
_auto_preview_timer_running = False
_last_render_backend = ""
_last_render_ms = 0.0


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


def _scene_from_project(project):
    scene = getattr(project, "id_data", None)
    return scene if scene is not None and hasattr(scene, "hotspot_project") else None


def _tag_all_image_editors():
    for window in getattr(bpy.context.window_manager, "windows", []):
        for area in getattr(window.screen, "areas", []):
            if area.type == "IMAGE_EDITOR":
                area.tag_redraw()


def _project_maps_missing(project, keys=MAP_KEYS):
    return any(bpy.data.images.get(getattr(project, MAP_IMAGE_ATTRS[key], "")) is None for key in keys)


def dirty_map_keys(project):
    if not getattr(project, "is_dirty", False):
        return set()
    keys = set(filter(None, getattr(project, "dirty_map_keys", "").split(",")))
    if not keys:
        keys.update(MAP_KEYS)
    return keys


def _set_dirty_map_keys(project, keys):
    keys = [key for key in MAP_KEYS if key in keys]
    project.dirty_map_keys = ",".join(keys)
    project.is_dirty = bool(keys)


def project_maps_dirty(project, keys=MAP_KEYS):
    return bool(dirty_map_keys(project).intersection(_normalize_map_keys(keys)))


def mark_project_clean(project, keys=MAP_KEYS):
    dirty = dirty_map_keys(project)
    dirty.difference_update(_normalize_map_keys(keys))
    _set_dirty_map_keys(project, dirty)


def _normalize_map_keys(keys):
    if isinstance(keys, str):
        keys = (keys,)
    normalized = []
    for key in keys:
        if key not in MAP_IMAGE_ATTRS:
            raise ValueError(f"Unsupported map key: {key}")
        if key not in normalized:
            normalized.append(key)
    return tuple(normalized)


def _selected_preview_key(project):
    key = getattr(project.settings, "preview_map", "ID")
    return key if key in MAP_IMAGE_ATTRS else "ID"


def show_project_preview(project, context=None):
    key = _selected_preview_key(project)
    image = bpy.data.images.get(getattr(project, MAP_IMAGE_ATTRS[key], ""))
    if image is None:
        if project.nodes and project.settings.auto_preview:
            mark_project_dirty(project, (key,))
        return None
    if context is None:
        image_io.show_image_in_open_editors(image)
    else:
        image_io.show_image_in_context(context, image)
    return image


def _image_float_buffer(key):
    return key in HEIGHT_DERIVED_MAP_KEYS


def _write_scene_map_images(scene, context, pixels_by_key, keys, resolution, clean):
    project = scene.hotspot_project
    settings = project.settings
    images = {}
    for key in keys:
        pixels = pixels_by_key[key]
        image = image_io.ensure_image(image_io.map_image_name(scene, MAP_SUFFIXES[key]), resolution, resolution, float_buffer=_image_float_buffer(key))
        image_io.write_pixels(image, pixels)
        setattr(project, MAP_IMAGE_ATTRS[key], image.name)
        images[key] = image

    if clean and resolution == settings.resolution:
        mark_project_clean(project, keys)
    if _selected_preview_key(project) in images:
        show_project_preview(project, context)
    return images


def _render_scene_maps_cpu(scene, context=None, keys=MAP_KEYS, resolution=None, clean=True):
    project = scene.hotspot_project
    keys = _normalize_map_keys(keys)
    settings = project.settings
    resolution = resolution or settings.resolution
    records = properties.nodes_to_records(project)
    leaves = derive_leaf_regions(records)
    pixels_by_key = {}

    if "ID" in keys:
        pixels_by_key["ID"] = render_id_pixels_from_leaves(
            leaves,
            resolution,
            resolution,
            seed=settings.color_seed,
            color_mode=settings.color_mode,
            background=tuple(settings.background_color),
            gutter_pixels=settings.gutter_pixels,
        )
    if "EDGE" in keys:
        pixels_by_key["EDGE"] = render_edge_pixels_from_leaves(leaves, resolution, resolution, settings.gutter_pixels, settings.edge_width_pixels)
    if "MASK" in keys:
        pixels_by_key["MASK"] = render_mask_pixels_from_leaves(
            leaves,
            resolution,
            resolution,
            settings.gutter_pixels,
            settings.mask_mode,
            settings.mask_size_pixels,
            settings.mask_softness_pixels,
            settings.mask_max_coverage,
            settings.mask_invert,
        )
    if any(key in HEIGHT_DERIVED_MAP_KEYS for key in keys):
        height_values = render_height_values_from_leaves(
            leaves,
            resolution,
            resolution,
            settings.gutter_pixels,
            settings.base_height,
            settings.height_depth,
            settings.bevel_width_pixels,
            settings.bevel_strength,
            settings.corner_radius_pixels,
            settings.edge_softness_pixels,
        )
        if "HEIGHT" in keys:
            pixels_by_key["HEIGHT"] = render_height_pixels_from_values(height_values)
        if "NORMAL" in keys:
            pixels_by_key["NORMAL"] = render_normal_pixels_from_height(height_values, resolution, resolution, settings.normal_strength, settings.normal_format == "DIRECTX", settings.normal_radius_pixels)
        if "AO" in keys:
            pixels_by_key["AO"] = render_ao_pixels_from_height(height_values, resolution, resolution, settings.ao_radius, settings.ao_strength)
        if "CURVATURE" in keys:
            pixels_by_key["CURVATURE"] = render_curvature_pixels_from_height(height_values, resolution, resolution, settings.curvature_strength, settings.curvature_radius_pixels)

    return _write_scene_map_images(scene, context, pixels_by_key, keys, resolution, clean)


def _render_scene_maps_gpu(scene, context=None, keys=MAP_KEYS, resolution=None, clean=True):
    keys = _normalize_map_keys(keys)
    resolution = resolution or scene.hotspot_project.settings.resolution
    from . import gpu_preview

    pixels_by_key = {key: gpu_preview.render_scene_map_pixels(scene, key, resolution) for key in keys}
    return _write_scene_map_images(scene, context, pixels_by_key, keys, resolution, clean)


def render_scene_maps(scene, context=None, keys=MAP_KEYS, resolution=None, clean=True):
    global _last_render_backend, _last_render_ms
    project = scene.hotspot_project
    if not project.nodes:
        raise RuntimeError("Create a hotspot canvas before rendering")

    keys = _normalize_map_keys(keys)
    start = time.perf_counter()
    try:
        images = _render_scene_maps_gpu(scene, context, keys, resolution, clean)
        _last_render_backend = "GPU"
        return images
    except Exception:
        images = _render_scene_maps_cpu(scene, context, keys, resolution, clean)
        _last_render_backend = "CPU fallback"
        return images
    finally:
        _last_render_ms = (time.perf_counter() - start) * 1000.0


def render_scene_id_map(scene, context=None):
    return render_scene_maps(scene, context, ("ID",))["ID"]


def render_project_id_map(context):
    return render_scene_id_map(context.scene, context)


def _log_preview_timing(project, key, backend, generation_ms, debounce_ms):
    debounce = "forced" if debounce_ms is None else f"{debounce_ms:.1f} ms debounce"
    message = f"Preview {key} {backend}: {generation_ms:.1f} ms generation after {debounce}"
    project.preview_status = f"{key} {backend} {generation_ms:.1f} ms, {debounce}"
    try:
        bpy.ops.hotspot.preview_log(message=message)
    except Exception:
        print(f"[Hotspot] {message}")


def render_scene_preview_map(scene, context=None, debounce_ms=None):
    project = scene.hotspot_project
    key = _selected_preview_key(project)
    start = time.perf_counter()
    try:
        from . import gpu_preview

        if gpu_preview.render_scene_preview(scene, key):
            _log_preview_timing(project, key, "GPU", (time.perf_counter() - start) * 1000.0, debounce_ms)
            return None
    except Exception:
        pass
    project.preview_status = "CPU fallback"
    image = _render_scene_maps_cpu(scene, context, (key,), project.settings.resolution, clean=False).get(key)
    _log_preview_timing(project, key, "CPU fallback", (time.perf_counter() - start) * 1000.0, debounce_ms)
    return image


def _auto_preview_timer(force=False):
    global _auto_preview_timer_running
    now = time.perf_counter()
    ready = []
    wait = []
    for scene_name in tuple(_auto_preview_scenes):
        elapsed = now - _auto_preview_scheduled_at.get(scene_name, now)
        if force or elapsed >= _AUTO_PREVIEW_DELAY:
            ready.append((scene_name, None if force else elapsed * 1000.0))
        else:
            wait.append(_AUTO_PREVIEW_DELAY - elapsed)

    for scene_name, debounce_ms in ready:
        _auto_preview_scenes.discard(scene_name)
        _auto_preview_scheduled_at.pop(scene_name, None)
        scene = bpy.data.scenes.get(scene_name)
        if scene is None or not hasattr(scene, "hotspot_project"):
            continue
        project = scene.hotspot_project
        key = _selected_preview_key(project)
        missing = _project_maps_missing(project, (key,))
        if project.nodes and project.settings.auto_preview and (project_maps_dirty(project, (key,)) or missing):
            try:
                render_scene_preview_map(scene, debounce_ms=debounce_ms)
            except Exception:
                pass
    _tag_all_image_editors()
    if _auto_preview_scenes:
        _auto_preview_timer_running = True
        return max(0.01, min(wait) if wait else _AUTO_PREVIEW_DELAY)
    _auto_preview_timer_running = False
    return None


def schedule_auto_preview(project):
    global _auto_preview_timer_running
    if not project.nodes or not project.settings.auto_preview:
        return
    scene = _scene_from_project(project)
    if scene is None:
        return
    key = _selected_preview_key(project)
    missing = _project_maps_missing(project, (key,))
    if not project_maps_dirty(project, (key,)) and not missing:
        return
    _auto_preview_scenes.add(scene.name)
    _auto_preview_scheduled_at[scene.name] = time.perf_counter()
    if not _auto_preview_timer_running:
        bpy.app.timers.register(_auto_preview_timer, first_interval=_AUTO_PREVIEW_DELAY)
        _auto_preview_timer_running = True


def cancel_auto_preview():
    global _auto_preview_timer_running
    _auto_preview_scenes.clear()
    _auto_preview_scheduled_at.clear()
    _auto_preview_timer_running = False
    try:
        if bpy.app.timers.is_registered(_auto_preview_timer):
            bpy.app.timers.unregister(_auto_preview_timer)
    except Exception:
        pass


def flush_auto_preview():
    try:
        if bpy.app.timers.is_registered(_auto_preview_timer):
            bpy.app.timers.unregister(_auto_preview_timer)
    except Exception:
        pass
    return _auto_preview_timer(force=True)


def mark_project_dirty(project, keys=MAP_KEYS):
    dirty = dirty_map_keys(project)
    dirty.update(_normalize_map_keys(keys))
    _set_dirty_map_keys(project, dirty)
    schedule_auto_preview(project)


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

    mark_project_dirty(project)
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
    mark_project_dirty(project)
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
        mark_project_dirty(project)
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
        project.edge_image_name = ""
        project.mask_image_name = ""
        project.height_image_name = ""
        project.normal_image_name = ""
        project.ao_image_name = ""
        project.curvature_image_name = ""
        mark_project_dirty(project)
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
    bl_label = "Render Maps"
    bl_description = "Generate the hotspot map images"
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
            images = render_scene_maps(context.scene, context)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        properties.clear_cut_preview(project_from_context(context))
        tag_hotspot_areas_for_redraw(context)
        self.report({"INFO"}, f"Rendered {len(images)} hotspot maps via {_last_render_backend} in {_last_render_ms:.1f} ms")
        return {"FINISHED"}


class HOTSPOT_OT_export_maps(bpy.types.Operator):
    bl_idname = "hotspot.export_maps"
    bl_label = "Export Maps"
    bl_description = "Export checked hotspot maps as PNG files"
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
        selected_keys = [key for key in MAP_KEYS if getattr(project.settings, MAP_EXPORT_ATTRS[key])]
        if not selected_keys:
            self.report({"WARNING"}, "Enable at least one map to export")
            return {"CANCELLED"}

        try:
            render_scene_maps(context.scene, context, selected_keys)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        paths = []
        for key in selected_keys:
            image = bpy.data.images.get(getattr(project, MAP_IMAGE_ATTRS[key], ""))
            if image is None:
                self.report({"ERROR"}, f"Missing generated {MAP_SUFFIXES[key]} map")
                return {"CANCELLED"}
            paths.append(
                image_io.export_image_png(
                    image,
                    project.settings.export_directory,
                    project.settings.export_stem,
                    MAP_SUFFIXES[key],
                )
            )
        properties.clear_cut_preview(project)
        tag_hotspot_areas_for_redraw(context)
        self.report({"INFO"}, f"Exported {len(paths)} map(s) via {_last_render_backend} render in {_last_render_ms:.1f} ms")
        return {"FINISHED"}


class HOTSPOT_OT_preview_log(bpy.types.Operator):
    bl_idname = "hotspot.preview_log"
    bl_label = "Hotspot Preview Log"
    bl_options = {"INTERNAL"}

    message: StringProperty(name="Message", default="")

    def execute(self, _context):
        self.report({"INFO"}, self.message)
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
    HOTSPOT_OT_preview_log,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    cancel_auto_preview()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
