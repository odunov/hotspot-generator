"""CPU rasterization for generated hotspot maps."""

from __future__ import annotations

import colorsys
import math
from array import array
from typing import Sequence

from .constants import COLOR_MODE_GRAYSCALE, COLOR_MODE_RANDOM, COLOR_MODE_STORED
from .model.layout import Bounds, LeafRegion

Color = tuple[float, float, float, float]


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


def leaf_color(leaf: LeafRegion, seed: int, mode: str) -> Color:
    if mode == COLOR_MODE_STORED:
        return tuple(clamp01(channel) for channel in leaf.color)  # type: ignore[return-value]
    if mode == COLOR_MODE_GRAYSCALE:
        return deterministic_color(leaf.node_id, seed, COLOR_MODE_GRAYSCALE)
    return deterministic_color(leaf.node_id, seed, COLOR_MODE_RANDOM)


def render_id_pixels_from_leaves(
    leaves: Sequence[LeafRegion],
    width: int,
    height: int,
    seed: int = 1337,
    color_mode: str = COLOR_MODE_RANDOM,
    background: Color = (0.0, 0.0, 0.0, 1.0),
) -> array:
    if width <= 0 or height <= 0:
        raise ValueError("Image dimensions must be positive")

    pixels = array("f", background) * (width * height)
    for leaf in leaves:
        x0, y0, x1, y1 = bounds_to_pixel_rect(leaf.bounds, width, height)
        if x0 >= x1 or y0 >= y1:
            continue

        color = array("f", leaf_color(leaf, seed, color_mode))
        row = color * (x1 - x0)
        row_len = len(row)
        for y in range(y0, y1):
            start = (y * width + x0) * 4
            pixels[start : start + row_len] = row
    return pixels

