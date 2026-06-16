"""CPU rasterization for generated hotspot maps."""

from __future__ import annotations

import colorsys
import math
from array import array
from typing import Sequence

from .constants import COLOR_MODE_GRAYSCALE, COLOR_MODE_RANDOM, COLOR_MODE_STORED, MASK_MODE_FILL, MASK_MODE_OVAL, MASK_MODE_SQUIRCLE
from .model.layout import Bounds, LeafRegion

Color = tuple[float, float, float, float]
_AO_RESPONSE = 4.0
_CURVATURE_RESPONSE = 8.0
# ponytail: fixed AO kernel; add quality presets only if profiling says this is too slow.
_DISK_SAMPLES = (
    (1.0, 0.0, 0.55),
    (0.7071, 0.7071, 0.55),
    (0.0, 1.0, 0.55),
    (-0.7071, 0.7071, 0.55),
    (-1.0, 0.0, 0.55),
    (-0.7071, -0.7071, 0.55),
    (0.0, -1.0, 0.55),
    (0.7071, -0.7071, 0.55),
    (0.4619, 0.1913, 1.0),
    (0.1913, 0.4619, 1.0),
    (-0.1913, 0.4619, 1.0),
    (-0.4619, 0.1913, 1.0),
    (-0.4619, -0.1913, 1.0),
    (-0.1913, -0.4619, 1.0),
    (0.1913, -0.4619, 1.0),
    (0.4619, -0.1913, 1.0),
)
_AO_SAMPLES = _DISK_SAMPLES
_CURVATURE_SAMPLES = _DISK_SAMPLES


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def deterministic_color(node_id: int, seed: int = 1337, mode: str = COLOR_MODE_RANDOM) -> Color:
    if mode == COLOR_MODE_GRAYSCALE:
        gray = ((node_id * 37 + seed) % 254 + 1) / 255.0
        return (gray, gray, gray, 1.0)

    hue = (node_id * 0.618033988749895 + (seed % 997) / 997.0) % 1.0
    saturation = 0.58
    value = 0.92
    r, g, b = colorsys.hsv_to_rgb(hue, saturation, value)
    return (r, g, b, 1.0)


def quantize_boundary(value: float, size: int) -> int:
    value = clamp01(value)
    return max(0, min(size, int(math.floor(value * size + 0.5))))


def bounds_to_pixel_rect(bounds: Bounds, width: int, height: int) -> tuple[int, int, int, int]:
    x0 = quantize_boundary(bounds.x0, width)
    x1 = quantize_boundary(bounds.x1, width)
    y0 = quantize_boundary(bounds.y0, height)
    y1 = quantize_boundary(bounds.y1, height)
    return x0, y0, x1, y1


def inset_pixel_rect(rect: tuple[int, int, int, int], gutter_pixels: int) -> tuple[int, int, int, int]:
    if gutter_pixels <= 0:
        return rect
    x0, y0, x1, y1 = rect
    inset_x = min(gutter_pixels, max(0, (x1 - x0 - 1) // 2))
    inset_y = min(gutter_pixels, max(0, (y1 - y0 - 1) // 2))
    return x0 + inset_x, y0 + inset_y, x1 - inset_x, y1 - inset_y


def leaf_color(leaf: LeafRegion, seed: int, mode: str, index: int = 0, count: int = 1) -> Color:
    if mode == COLOR_MODE_STORED:
        return tuple(clamp01(channel) for channel in leaf.color)  # type: ignore[return-value]
    if mode == COLOR_MODE_GRAYSCALE:
        gray = (index + 1) / (max(1, count) + 1)
        return (gray, gray, gray, 1.0)
    return deterministic_color(leaf.node_id, seed, COLOR_MODE_RANDOM)


def render_id_pixels_from_leaves(
    leaves: Sequence[LeafRegion],
    width: int,
    height: int,
    seed: int = 1337,
    color_mode: str = COLOR_MODE_RANDOM,
    background: Color = (0.0, 0.0, 0.0, 1.0),
    gutter_pixels: int = 0,
) -> array:
    if width <= 0 or height <= 0:
        raise ValueError("Image dimensions must be positive")

    pixels = array("f", background) * (width * height)
    for index, leaf in enumerate(leaves):
        x0, y0, x1, y1 = inset_pixel_rect(bounds_to_pixel_rect(leaf.bounds, width, height), gutter_pixels)
        if x0 >= x1 or y0 >= y1:
            continue

        color = array("f", leaf_color(leaf, seed, color_mode, index, len(leaves)))
        row = color * (x1 - x0)
        row_len = len(row)
        for y in range(y0, y1):
            start = (y * width + x0) * 4
            pixels[start : start + row_len] = row
    return pixels


def render_mask_pixels_from_leaves(
    leaves: Sequence[LeafRegion],
    width: int,
    height: int,
    gutter_pixels: int = 0,
    mask_mode: str = MASK_MODE_FILL,
    mask_size_pixels: int = 64,
    mask_softness_pixels: int = 32,
    mask_max_coverage: float = 0.45,
    invert: bool = False,
) -> array:
    if width <= 0 or height <= 0:
        raise ValueError("Image dimensions must be positive")
    pixels = array("f", (0.0, 0.0, 0.0, 1.0)) * (width * height)
    fill = array("f", (0.0, 0.0, 0.0, 1.0) if invert else (1.0, 1.0, 1.0, 1.0))
    for leaf in leaves:
        x0, y0, x1, y1 = inset_pixel_rect(bounds_to_pixel_rect(leaf.bounds, width, height), gutter_pixels)
        row = fill * max(0, x1 - x0)
        for y in range(y0, y1):
            start = (y * width + x0) * 4
            if mask_mode == MASK_MODE_FILL:
                pixels[start : start + len(row)] = row
                continue
            for x in range(x0, x1):
                gray = _mask_value(x, y, (x0, y0, x1, y1), mask_mode, mask_size_pixels, mask_softness_pixels, mask_max_coverage)
                if invert:
                    gray = 1.0 - gray
                index = (y * width + x) * 4
                pixels[index : index + 4] = array("f", (gray, gray, gray, 1.0))
    return pixels


def _smoothstep(edge0: float, edge1: float, value: float) -> float:
    if edge1 <= edge0:
        return 1.0 if value >= edge1 else 0.0
    t = clamp01((value - edge0) / (edge1 - edge0))
    return t * t * (3.0 - 2.0 * t)


def _mask_value(x: int, y: int, rect: tuple[int, int, int, int], mask_mode: str, size_pixels: int, softness_pixels: int, max_coverage: float) -> float:
    if size_pixels <= 0:
        return 0.0
    x0, y0, x1, y1 = rect
    rect_width = max(1.0, float(x1 - x0))
    rect_height = max(1.0, float(y1 - y0))
    nx = ((x + 0.5) - (x0 + rect_width * 0.5)) / (rect_width * 0.5)
    ny = ((y + 0.5) - (y0 + rect_height * 0.5)) / (rect_height * 0.5)
    if mask_mode == MASK_MODE_OVAL:
        shape_distance = math.hypot(nx, ny)
    else:
        shape_distance = (abs(nx) ** 4.0 + abs(ny) ** 4.0) ** 0.25
    edge_distance = max(0.0, 1.0 - shape_distance) * min(rect_width, rect_height) * 0.5
    size = min(float(size_pixels), min(rect_width, rect_height) * clamp01(max_coverage))
    softness = min(max(0.0, float(softness_pixels)), size)
    if softness <= 0.0:
        return 1.0 if edge_distance <= size else 0.0
    return 1.0 - _smoothstep(max(0.0, size - softness), size, edge_distance)


def render_edge_pixels_from_leaves(
    leaves: Sequence[LeafRegion],
    width: int,
    height: int,
    gutter_pixels: int = 0,
    edge_width_pixels: int = 2,
) -> array:
    if width <= 0 or height <= 0:
        raise ValueError("Image dimensions must be positive")
    pixels = array("f", (0.0, 0.0, 0.0, 1.0)) * (width * height)
    white = array("f", (1.0, 1.0, 1.0, 1.0))
    for leaf in leaves:
        x0, y0, x1, y1 = inset_pixel_rect(bounds_to_pixel_rect(leaf.bounds, width, height), gutter_pixels)
        edge_width = max(1, min(edge_width_pixels, max(1, (x1 - x0 + 1) // 2), max(1, (y1 - y0 + 1) // 2)))
        full = white * max(0, x1 - x0)
        side = white * min(edge_width, max(0, x1 - x0))
        for y in range(y0, y1):
            start = (y * width + x0) * 4
            if y - y0 < edge_width or y1 - 1 - y < edge_width:
                pixels[start : start + len(full)] = full
                continue
            pixels[start : start + len(side)] = side
            end_start = (y * width + max(x0, x1 - edge_width)) * 4
            pixels[end_start : end_start + len(side)] = side
    return pixels


def grayscale_pixels(values: Sequence[float]) -> array:
    pixels = array("f")
    for value in values:
        gray = clamp01(value)
        pixels.extend((gray, gray, gray, 1.0))
    return pixels


def _rounded_rect_sdf(cx: float, cy: float, rect: tuple[int, int, int, int], radius: float) -> float:
    x0, y0, x1, y1 = rect
    hx = (x1 - x0) * 0.5
    hy = (y1 - y0) * 0.5
    radius = min(max(0.0, radius), max(0.0, hx - 0.5), max(0.0, hy - 0.5))
    px = abs(cx - (x0 + hx)) - (hx - radius)
    py = abs(cy - (y0 + hy)) - (hy - radius)
    outside = math.hypot(max(px, 0.0), max(py, 0.0))
    inside = min(max(px, py), 0.0)
    return outside + inside - radius


def render_height_values_from_leaves(
    leaves: Sequence[LeafRegion],
    width: int,
    height: int,
    gutter_pixels: int = 0,
    base_height: float = 0.5,
    height_depth: float = 0.35,
    bevel_width_pixels: int = 8,
    bevel_strength: float = 1.0,
    corner_radius_pixels: int = 0,
    edge_softness_pixels: int = 0,
) -> array:
    if width <= 0 or height <= 0:
        raise ValueError("Image dimensions must be positive")

    values = array("f", (0.0,)) * (width * height)
    ramp_width = max(0, bevel_width_pixels) + max(0, edge_softness_pixels)
    power = max(0.01, bevel_strength)
    for leaf in leaves:
        rect = inset_pixel_rect(bounds_to_pixel_rect(leaf.bounds, width, height), gutter_pixels)
        x0, y0, x1, y1 = rect
        if x0 >= x1 or y0 >= y1:
            continue
        for y in range(y0, y1):
            for x in range(x0, x1):
                sdf = _rounded_rect_sdf(x + 0.5, y + 0.5, rect, corner_radius_pixels)
                if sdf > 0.0:
                    continue
                distance = -sdf
                if ramp_width <= 0:
                    ramp = 1.0
                else:
                    t = clamp01(distance / ramp_width)
                    ramp = t * t * (3.0 - 2.0 * t)
                values[y * width + x] = clamp01(base_height + height_depth * (ramp**power))
    return values


def render_height_pixels_from_values(height_values: Sequence[float]) -> array:
    return grayscale_pixels(height_values)


def _height_at(height_values: Sequence[float], width: int, height: int, x: int, y: int) -> float:
    return height_values[max(0, min(height - 1, y)) * width + max(0, min(width - 1, x))]


def _height_gradient_from_height(height_values: Sequence[float], width: int, height: int, x: int, y: int, radius: int = 1) -> tuple[float, float]:
    radius = max(1, radius)
    tl = _height_at(height_values, width, height, x - radius, y + radius)
    tc = _height_at(height_values, width, height, x, y + radius)
    tr = _height_at(height_values, width, height, x + radius, y + radius)
    ml = _height_at(height_values, width, height, x - radius, y)
    mr = _height_at(height_values, width, height, x + radius, y)
    bl = _height_at(height_values, width, height, x - radius, y - radius)
    bc = _height_at(height_values, width, height, x, y - radius)
    br = _height_at(height_values, width, height, x + radius, y - radius)
    scale = 0.25 / radius
    return ((tr + 2.0 * mr + br - tl - 2.0 * ml - bl) * scale, (tl + 2.0 * tc + tr - bl - 2.0 * bc - br) * scale)


def render_normal_pixels_from_height(height_values: Sequence[float], width: int, height: int, strength: float = 2.0, directx: bool = False, radius: int = 1) -> array:
    pixels = array("f")
    for y in range(height):
        for x in range(width):
            dx, dy = _height_gradient_from_height(height_values, width, height, x, y, radius)
            dx *= strength
            dy *= strength
            length = math.sqrt(dx * dx + dy * dy + 1.0)
            red = (-dx / length) * 0.5 + 0.5
            green = (-dy / length) * 0.5 + 0.5
            if directx:
                green = 1.0 - green
            blue = 1.0 / length * 0.5 + 0.5
            pixels.extend((clamp01(red), clamp01(green), clamp01(blue), 1.0))
    return pixels


def render_ao_pixels_from_height(height_values: Sequence[float], width: int, height: int, radius: int = 4, strength: float = 1.0) -> array:
    radius = max(1, radius)
    total_weight = sum(sample[2] for sample in _AO_SAMPLES)
    out = array("f")
    for y in range(height):
        for x in range(width):
            h = height_values[y * width + x]
            rise = 0.0
            for offset_x, offset_y, weight in _AO_SAMPLES:
                sample_x = max(0, min(width - 1, int(round(x + offset_x * radius))))
                sample_y = max(0, min(height - 1, int(round(y + offset_y * radius))))
                rise += max(0.0, height_values[sample_y * width + sample_x] - h) * weight
            gray = 1.0 - clamp01((rise / total_weight) * strength * _AO_RESPONSE)
            out.extend((gray, gray, gray, 1.0))
    return out


def _normal_xy_from_height(height_values: Sequence[float], width: int, height: int, x: int, y: int) -> tuple[float, float]:
    dx, dy = _height_gradient_from_height(height_values, width, height, x, y)
    length = math.sqrt(dx * dx + dy * dy + 1.0)
    return -dx / length, -dy / length


def render_curvature_pixels_from_height(height_values: Sequence[float], width: int, height: int, strength: float = 1.0, radius: int = 4) -> array:
    radius = max(1, radius)
    total_weight = sum(sample[2] for sample in _CURVATURE_SAMPLES)
    out = array("f")
    for y in range(height):
        for x in range(width):
            normal_x, normal_y = _normal_xy_from_height(height_values, width, height, x, y)
            bend = 0.0
            for offset_x, offset_y, weight in _CURVATURE_SAMPLES:
                sample_x = max(0, min(width - 1, int(round(x + offset_x * radius))))
                sample_y = max(0, min(height - 1, int(round(y + offset_y * radius))))
                sample_normal_x, sample_normal_y = _normal_xy_from_height(height_values, width, height, sample_x, sample_y)
                direction_length = math.hypot(offset_x, offset_y)
                bend += ((sample_normal_x - normal_x) * offset_x + (sample_normal_y - normal_y) * offset_y) * weight / direction_length
            gray = clamp01(0.5 + (bend / total_weight) * strength * _CURVATURE_RESPONSE)
            out.extend((gray, gray, gray, 1.0))
    return out

