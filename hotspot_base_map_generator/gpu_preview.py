"""GPU-backed live preview for hotspot maps."""

from __future__ import annotations

from datetime import datetime
import math
from pathlib import Path
import tempfile
import traceback

import bpy

from . import properties
from .constants import HEIGHT_DERIVED_MAP_KEYS, MAP_KEYS
from .model.layout import derive_leaf_regions
from .raster import bounds_to_pixel_rect, inset_pixel_rect, leaf_color

_handler = None
_states = {}
_shaders = {}
_batches = {}
_LOG_FILENAME = "hotspot_base_map_generator.log"

_LEAF_VERTEX = """
void main()
{
    uv = pos * 0.5 + 0.5;
    gl_Position = vec4(pos, 0.0, 1.0);
}
"""

_LEAF_FRAGMENT = """
float hotspot_clamp01(float value)
{
    return clamp(value, 0.0, 1.0);
}

float hotspot_rounded_rect_sdf(vec2 center, vec4 rect, float corner_radius)
{
    float hx = (rect.z - rect.x) * 0.5;
    float hy = (rect.w - rect.y) * 0.5;
    float radius = min(max(0.0, corner_radius), min(max(0.0, hx - 0.5), max(0.0, hy - 0.5)));
    vec2 half_size = vec2(hx, hy);
    vec2 rect_center = vec2(rect.x + hx, rect.y + hy);
    vec2 q = abs(center - rect_center) - (half_size - vec2(radius));
    float outside = length(max(q, vec2(0.0)));
    float inside = min(max(q.x, q.y), 0.0);
    return outside + inside - radius;
}

float hotspot_mask_value(vec2 pixel, vec4 rect)
{
    if (mask_mode == 0 || mask_size <= 0.0) {
        float gray = mask_mode == 0 ? 1.0 : 0.0;
        return mask_invert ? 1.0 - gray : gray;
    }
    vec2 rect_size = max(rect.zw - rect.xy, vec2(1.0));
    vec2 rect_center = rect.xy + rect_size * 0.5;
    vec2 p = (pixel + vec2(0.5) - rect_center) / (rect_size * 0.5);
    float shape_distance = length(p);
    if (mask_mode == 2) {
        shape_distance = pow(pow(abs(p.x), 4.0) + pow(abs(p.y), 4.0), 0.25);
    }
    float edge_distance = max(0.0, 1.0 - shape_distance) * min(rect_size.x, rect_size.y) * 0.5;
    float capped_size = min(mask_size, min(rect_size.x, rect_size.y) * clamp(mask_max_coverage, 0.0, 1.0));
    float softness = min(max(0.0, mask_softness), capped_size);
    float gray = softness <= 0.0 ? (edge_distance <= capped_size ? 1.0 : 0.0) : 1.0 - smoothstep(max(0.0, capped_size - softness), capped_size, edge_distance);
    return mask_invert ? 1.0 - gray : gray;
}

void main()
{
    vec2 pixel = floor(uv * resolution);
    if (pixel.x < rect.x || pixel.y < rect.y || pixel.x >= rect.z || pixel.y >= rect.w) {
        discard;
    }

    if (map_mode == 0) {
        fragColor = fill_color;
        return;
    }
    if (map_mode == 1) {
        float dx = min(pixel.x - rect.x, rect.z - 1.0 - pixel.x);
        float dy = min(pixel.y - rect.y, rect.w - 1.0 - pixel.y);
        float edge = min(dx, dy);
        fragColor = edge < edge_width ? vec4(1.0) : vec4(0.0, 0.0, 0.0, 1.0);
        return;
    }
    if (map_mode == 2) {
        float gray = hotspot_mask_value(pixel, rect);
        fragColor = vec4(gray, gray, gray, 1.0);
        return;
    }

    float sdf = hotspot_rounded_rect_sdf(pixel + vec2(0.5), rect, corner_radius);
    if (sdf > 0.0) {
        discard;
    }
    float ramp_width = max(0.0, bevel_width) + max(0.0, edge_softness);
    float ramp = 1.0;
    if (ramp_width > 0.0) {
        float t = hotspot_clamp01(-sdf / ramp_width);
        ramp = t * t * (3.0 - 2.0 * t);
    }
    float gray = hotspot_clamp01(base_height + height_depth * pow(ramp, max(0.01, bevel_strength)));
    fragColor = vec4(gray, gray, gray, 1.0);
}
"""

_DERIVED_VERTEX = """
void main()
{
    uv = pos * 0.5 + 0.5;
    gl_Position = vec4(pos, 0.0, 1.0);
}
"""

_DERIVED_FRAGMENT = """
const float HOTSPOT_AO_RESPONSE = 4.0;
const float HOTSPOT_CURVATURE_RESPONSE = 8.0;

float hotspot_height_at(vec2 pixel)
{
    vec2 clamped_pixel = clamp(pixel, vec2(0.0), resolution - vec2(1.0));
    return texelFetch(height_tex, ivec2(floor(clamped_pixel + vec2(0.5))), 0).r;
}

vec3 hotspot_disk_sample(int index)
{
    if (index == 0) return vec3(1.0, 0.0, 0.55);
    if (index == 1) return vec3(0.7071, 0.7071, 0.55);
    if (index == 2) return vec3(0.0, 1.0, 0.55);
    if (index == 3) return vec3(-0.7071, 0.7071, 0.55);
    if (index == 4) return vec3(-1.0, 0.0, 0.55);
    if (index == 5) return vec3(-0.7071, -0.7071, 0.55);
    if (index == 6) return vec3(0.0, -1.0, 0.55);
    if (index == 7) return vec3(0.7071, -0.7071, 0.55);
    if (index == 8) return vec3(0.4619, 0.1913, 1.0);
    if (index == 9) return vec3(0.1913, 0.4619, 1.0);
    if (index == 10) return vec3(-0.1913, 0.4619, 1.0);
    if (index == 11) return vec3(-0.4619, 0.1913, 1.0);
    if (index == 12) return vec3(-0.4619, -0.1913, 1.0);
    if (index == 13) return vec3(-0.1913, -0.4619, 1.0);
    if (index == 14) return vec3(0.1913, -0.4619, 1.0);
    return vec3(0.4619, -0.1913, 1.0);
}

vec2 hotspot_height_gradient_at(vec2 pixel, float radius)
{
    float r = max(1.0, radius);
    float tl = hotspot_height_at(pixel + vec2(-r, r));
    float tc = hotspot_height_at(pixel + vec2(0.0, r));
    float tr = hotspot_height_at(pixel + vec2(r, r));
    float ml = hotspot_height_at(pixel + vec2(-r, 0.0));
    float mr = hotspot_height_at(pixel + vec2(r, 0.0));
    float bl = hotspot_height_at(pixel + vec2(-r, -r));
    float bc = hotspot_height_at(pixel + vec2(0.0, -r));
    float br = hotspot_height_at(pixel + vec2(r, -r));
    float scale = 0.25 / r;
    return vec2((tr + 2.0 * mr + br - tl - 2.0 * ml - bl) * scale, (tl + 2.0 * tc + tr - bl - 2.0 * bc - br) * scale);
}

vec2 hotspot_normal_xy_at(vec2 pixel)
{
    vec2 gradient = hotspot_height_gradient_at(pixel, 1.0);
    vec3 normal = normalize(vec3(-gradient.x, -gradient.y, 1.0));
    return normal.xy;
}

void main()
{
    vec2 pixel = floor(uv * resolution);
    float h = hotspot_height_at(pixel);

    if (map_mode == 0) {
        vec2 gradient = hotspot_height_gradient_at(pixel, float(normal_radius));
        float dx = gradient.x * normal_strength;
        float dy = gradient.y * normal_strength;
        float len = sqrt(dx * dx + dy * dy + 1.0);
        float red = (-dx / len) * 0.5 + 0.5;
        float green = (-dy / len) * 0.5 + 0.5;
        if (normal_directx) {
            green = 1.0 - green;
        }
        float blue = (1.0 / len) * 0.5 + 0.5;
        fragColor = vec4(clamp(red, 0.0, 1.0), clamp(green, 0.0, 1.0), clamp(blue, 0.0, 1.0), 1.0);
        return;
    }

    if (map_mode == 1) {
        float rise = 0.0;
        float weight_sum = 0.0;
        for (int index = 0; index < 16; index++) {
            vec3 sample_info = hotspot_disk_sample(index);
            float sample_height = hotspot_height_at(pixel + sample_info.xy * float(ao_radius));
            rise += max(0.0, sample_height - h) * sample_info.z;
            weight_sum += sample_info.z;
        }
        float gray = 1.0 - clamp((rise / weight_sum) * ao_strength * HOTSPOT_AO_RESPONSE, 0.0, 1.0);
        fragColor = vec4(gray, gray, gray, 1.0);
        return;
    }

    vec2 center_normal = hotspot_normal_xy_at(pixel);
    float bend = 0.0;
    float weight_sum = 0.0;
    for (int index = 0; index < 16; index++) {
        vec3 sample_info = hotspot_disk_sample(index);
        vec2 sample_normal = hotspot_normal_xy_at(pixel + sample_info.xy * float(curvature_radius));
        bend += dot(sample_normal - center_normal, normalize(sample_info.xy)) * sample_info.z;
        weight_sum += sample_info.z;
    }
    float gray = clamp(0.5 + (bend / weight_sum) * curvature_strength * HOTSPOT_CURVATURE_RESPONSE, 0.0, 1.0);
    fragColor = vec4(gray, gray, gray, 1.0);
}
"""


def _shader(name):
    shader = _shaders.get(name)
    if shader is not None:
        return shader

    import gpu

    iface = gpu.types.GPUStageInterfaceInfo(f"hotspot_{name}_iface")
    iface.smooth("VEC2", "uv")
    info = gpu.types.GPUShaderCreateInfo()
    info.vertex_in(0, "VEC2", "pos")
    info.vertex_out(iface)
    info.fragment_out(0, "VEC4", "fragColor")
    info.push_constant("INT", "map_mode")
    info.push_constant("VEC2", "resolution")
    if name == "leaf":
        info.push_constant("VEC4", "rect")
        info.push_constant("VEC4", "fill_color")
        info.push_constant("FLOAT", "edge_width")
        info.push_constant("INT", "mask_mode")
        info.push_constant("FLOAT", "mask_size")
        info.push_constant("FLOAT", "mask_softness")
        info.push_constant("FLOAT", "mask_max_coverage")
        info.push_constant("BOOL", "mask_invert")
        info.push_constant("FLOAT", "base_height")
        info.push_constant("FLOAT", "height_depth")
        info.push_constant("FLOAT", "bevel_width")
        info.push_constant("FLOAT", "bevel_strength")
        info.push_constant("FLOAT", "corner_radius")
        info.push_constant("FLOAT", "edge_softness")
        info.vertex_source(_LEAF_VERTEX)
        info.fragment_source(_LEAF_FRAGMENT)
    else:
        info.sampler(0, "FLOAT_2D", "height_tex")
        info.push_constant("INT", "normal_radius")
        info.push_constant("FLOAT", "normal_strength")
        info.push_constant("BOOL", "normal_directx")
        info.push_constant("INT", "ao_radius")
        info.push_constant("FLOAT", "ao_strength")
        info.push_constant("INT", "curvature_radius")
        info.push_constant("FLOAT", "curvature_strength")
        info.vertex_source(_DERIVED_VERTEX)
        info.fragment_source(_DERIVED_FRAGMENT)
    shader = gpu.shader.create_from_info(info)
    _shaders[name] = shader
    return shader


def _batch(shader):
    batch = _batches.get(shader.name)
    if batch is not None:
        return batch

    from gpu_extras.batch import batch_for_shader

    batch = batch_for_shader(
        shader,
        "TRIS",
        {"pos": ((-1.0, -1.0), (1.0, -1.0), (-1.0, 1.0), (1.0, 1.0))},
        indices=((0, 1, 2), (2, 1, 3)),
    )
    _batches[shader.name] = batch
    return batch


def _free_state(state):
    for key in ("preview", "height"):
        offscreen = state.get(key)
        if offscreen is not None:
            try:
                offscreen.free()
            except Exception:
                pass


def log_gpu_failure(exc, key):
    try:
        config_dir = bpy.utils.user_resource("CONFIG") or tempfile.gettempdir()
        path = Path(config_dir) / _LOG_FILENAME
        import gpu

        shader_name = "derived" if key in HEIGHT_DERIVED_MAP_KEYS else "leaf"
        shader_source = _DERIVED_FRAGMENT if shader_name == "derived" else _LEAF_FRAGMENT
        with path.open("a", encoding="utf-8") as log:
            log.write(f"\n{'=' * 72}\n{datetime.now().isoformat(timespec='seconds')} GPU failure ({key})\n")
            log.write(f"Blender: {bpy.app.version_string}\n")
            for name in ("backend_type_get", "vendor_get", "renderer_get", "version_get"):
                getter = getattr(gpu.platform, name, None)
                if getter is not None:
                    try:
                        value = getter()
                    except Exception:
                        value = "<unavailable>"
                    log.write(f"{name[:-4]}: {value}\n")
            log.write(f"Error: {exc!r}\n{traceback.format_exc()}\nShader ({shader_name}):\n{shader_source}\n")
        print(f"[Hotspot] GPU failure logged to {path}")
        return str(path)
    except Exception:
        return ""


def _opaque_draw_state():
    import gpu

    try:
        gpu.state.blend_set("NONE")
    except Exception:
        pass
    try:
        gpu.state.depth_test_set("NONE")
    except Exception:
        pass


def _state(scene, width, height):
    import gpu

    key = scene.name
    state = _states.get(key)
    if state is not None and state.get("size") == (width, height):
        return state
    if state is not None:
        _free_state(state)
    state = {
        "size": (width, height),
        "preview": gpu.types.GPUOffScreen(width, height, format="RGBA32F"),
        "height": gpu.types.GPUOffScreen(width, height, format="RGBA32F"),
        "key": "",
        "valid": False,
    }
    _states[key] = state
    return state


def _tag_all_image_editors():
    for window in getattr(bpy.context.window_manager, "windows", []):
        for area in getattr(window.screen, "areas", []):
            if area.type == "IMAGE_EDITOR":
                area.tag_redraw()


def _draw_leaf_map(offscreen, project, leaves, key, resolution=None):
    import gpu

    settings = project.settings
    width = int(resolution or settings.resolution)
    height = width
    clear = tuple(settings.background_color) if key == "ID" else (0.0, 0.0, 0.0, 1.0)
    mode = {"ID": 0, "EDGE": 1, "MASK": 2, "HEIGHT": 3}[key]
    shader = _shader("leaf")
    batch = _batch(shader)

    with offscreen.bind():
        _opaque_draw_state()
        gpu.state.viewport_set(0, 0, width, height)
        gpu.state.active_framebuffer_get().clear(color=clear)
        for index, leaf in enumerate(leaves):
            rect = inset_pixel_rect(bounds_to_pixel_rect(leaf.bounds, width, height), settings.gutter_pixels)
            if rect[0] >= rect[2] or rect[1] >= rect[3]:
                continue
            shader.bind()
            shader.uniform_int("map_mode", mode)
            shader.uniform_float("resolution", (float(width), float(height)))
            shader.uniform_float("rect", tuple(float(value) for value in rect))
            color = leaf_color(leaf, settings.color_seed, settings.color_mode, index, len(leaves))
            shader.uniform_float("fill_color", tuple(color))
            shader.uniform_float("edge_width", float(settings.edge_width_pixels))
            shader.uniform_int("mask_mode", {"FILL": 0, "OVAL": 1, "SQUIRCLE": 2}.get(settings.mask_mode, 2))
            shader.uniform_float("mask_size", float(settings.mask_size_pixels))
            shader.uniform_float("mask_softness", float(settings.mask_softness_pixels))
            shader.uniform_float("mask_max_coverage", float(settings.mask_max_coverage))
            shader.uniform_bool("mask_invert", bool(settings.mask_invert))
            shader.uniform_float("base_height", float(settings.base_height))
            shader.uniform_float("height_depth", float(settings.height_depth))
            shader.uniform_float("bevel_width", float(settings.bevel_width_pixels))
            shader.uniform_float("bevel_strength", float(settings.bevel_strength))
            shader.uniform_float("corner_radius", float(settings.corner_radius_pixels))
            shader.uniform_float("edge_softness", float(settings.edge_softness_pixels))
            batch.draw(shader)


def _draw_derived_map(preview, height, project, key, resolution=None):
    import gpu

    settings = project.settings
    width = int(resolution or settings.resolution)
    shader = _shader("derived")
    batch = _batch(shader)
    mode = {"NORMAL": 0, "AO": 1, "CURVATURE": 2}[key]

    with preview.bind():
        _opaque_draw_state()
        gpu.state.viewport_set(0, 0, width, width)
        gpu.state.active_framebuffer_get().clear(color=(0.0, 0.0, 0.0, 1.0))
        shader.bind()
        shader.uniform_int("map_mode", mode)
        shader.uniform_float("resolution", (float(width), float(width)))
        shader.uniform_sampler("height_tex", height.texture_color)
        shader.uniform_int("normal_radius", int(settings.normal_radius_pixels))
        shader.uniform_float("normal_strength", float(settings.normal_strength))
        shader.uniform_bool("normal_directx", settings.normal_format == "DIRECTX")
        shader.uniform_int("ao_radius", int(settings.ao_radius))
        shader.uniform_float("ao_strength", float(settings.ao_strength))
        shader.uniform_int("curvature_radius", int(settings.curvature_radius_pixels))
        shader.uniform_float("curvature_strength", float(settings.curvature_strength))
        batch.draw(shader)


def _draw_map(preview, height, project, leaves, key, resolution):
    if key in HEIGHT_DERIVED_MAP_KEYS and key != "HEIGHT":
        if height is None:
            raise RuntimeError("Height offscreen is required for derived maps")
        _draw_leaf_map(height, project, leaves, "HEIGHT", resolution)
        _draw_derived_map(preview, height, project, key, resolution)
    else:
        _draw_leaf_map(preview, project, leaves, key, resolution)


def _validate_pixels(pixels, resolution):
    expected = resolution * resolution * 4
    if len(pixels) != expected:
        raise RuntimeError(f"GPU readback returned {len(pixels)} floats, expected {expected}")
    step = max(1, len(pixels) // 4096)
    for index in range(0, len(pixels), step):
        value = pixels[index]
        if not math.isfinite(value) or value < -0.001 or value > 1.001:
            raise RuntimeError(f"GPU readback produced invalid value {value}")
    return pixels


def render_scene_map_pixels(scene, key, resolution):
    if key not in MAP_KEYS:
        raise ValueError(f"Unsupported map key: {key}")

    import gpu

    resolution = int(resolution)
    project = scene.hotspot_project
    records = properties.nodes_to_records(project)
    leaves = derive_leaf_regions(records)
    preview = gpu.types.GPUOffScreen(resolution, resolution, format="RGBA32F")
    height = gpu.types.GPUOffScreen(resolution, resolution, format="RGBA32F") if key in HEIGHT_DERIVED_MAP_KEYS and key != "HEIGHT" else None
    try:
        _draw_map(preview, height, project, leaves, key, resolution)
        with preview.bind():
            pixels = gpu.types.Buffer("FLOAT", resolution * resolution * 4)
            gpu.state.active_framebuffer_get().read_color(0, 0, resolution, resolution, 4, 0, "FLOAT", data=pixels)
        return _validate_pixels(pixels, resolution)
    finally:
        preview.free()
        if height is not None:
            height.free()


def render_scene_preview(scene, key):
    if key not in MAP_KEYS:
        return False
    project = scene.hotspot_project
    width = project.settings.resolution
    state = _state(scene, width, width)
    records = properties.nodes_to_records(project)
    leaves = derive_leaf_regions(records)

    _draw_map(state["preview"], state["height"], project, leaves, key, width)

    state["key"] = key
    state["valid"] = True
    project.preview_status = "GPU"
    _tag_all_image_editors()
    return True


def _draw_preview():
    try:
        context = bpy.context
        area = context.area
        region = context.region
        scene = context.scene
        if area is None or region is None or area.type != "IMAGE_EDITOR":
            return
        project = scene.hotspot_project
        if " GPU " not in f" {project.preview_status} ":
            return
        state = _states.get(scene.name)
        if state is None or not state.get("valid") or state.get("key") != project.settings.preview_map:
            return

        from gpu_extras.presets import draw_texture_2d

        x0, y0 = region.view2d.view_to_region(0.0, 0.0, clip=False)
        x1, y1 = region.view2d.view_to_region(1.0, 1.0, clip=False)
        x = min(x0, x1)
        y = min(y0, y1)
        width = abs(x1 - x0)
        height = abs(y1 - y0)
        if width <= 0 or height <= 0:
            return
        _opaque_draw_state()
        draw_texture_2d(state["preview"].texture_color, (x, y), width, height)
    except Exception:
        return


def register():
    global _handler
    if _handler is None:
        _handler = bpy.types.SpaceImageEditor.draw_handler_add(_draw_preview, (), "WINDOW", "POST_PIXEL")


def unregister():
    global _handler
    if _handler is not None:
        bpy.types.SpaceImageEditor.draw_handler_remove(_handler, "WINDOW")
        _handler = None
    for state in list(_states.values()):
        _free_state(state)
    _states.clear()
    _shaders.clear()
    _batches.clear()
