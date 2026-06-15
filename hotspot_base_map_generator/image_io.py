"""Blender Image datablock helpers."""

import os
import re

import bpy

from .constants import IMAGE_PREFIX


def safe_name(value):
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return value or "Scene"


def id_image_name(scene):
    return f"{IMAGE_PREFIX}_{safe_name(scene.name)}_ID"


def ensure_image(name, width, height):
    image = bpy.data.images.get(name)
    if image is None:
        image = bpy.data.images.new(name, width=width, height=height, alpha=True, float_buffer=False)
    elif tuple(image.size) != (width, height):
        image.scale(width, height)

    image.use_fake_user = True
    try:
        image.alpha_mode = "STRAIGHT"
    except Exception:
        pass
    try:
        image.colorspace_settings.name = "Non-Color"
    except Exception:
        pass
    return image


def write_pixels(image, pixels):
    expected = image.size[0] * image.size[1] * 4
    if len(pixels) != expected:
        raise ValueError(f"Pixel buffer length {len(pixels)} does not match image size {expected}")
    image.pixels.foreach_set(pixels)
    image.update()


def show_image_in_context(context, image):
    space = getattr(context, "space_data", None)
    if space is not None and getattr(space, "type", None) == "IMAGE_EDITOR":
        space.image = image


def export_image_png(image, directory, filename_stem, suffix="ID"):
    directory = bpy.path.abspath(directory or "//")
    os.makedirs(directory, exist_ok=True)
    filename = f"{safe_name(filename_stem)}_{suffix}.png"
    path = os.path.join(directory, filename)

    image.filepath_raw = path
    image.file_format = "PNG"
    image.save()
    return path

